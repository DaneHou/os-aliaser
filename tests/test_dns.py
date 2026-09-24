"""The stdlib DNS client, and TTL-driven scheduling."""
import concurrent.futures
import socket
import struct
import threading
import time

import pytest

from conftest import watcher


def name(n):
    return b''.join(bytes([len(p)]) + p.encode() for p in n.split('.')) + b'\0'


def rr(owner, rtype, ttl, rdata):
    return owner + struct.pack('>HHIH', rtype, 1, ttl, len(rdata)) + rdata


def reply(query, answers=(), rcode=0, txid=None, question=None):
    header = (txid or query[:2]) + struct.pack('>HHHHH', 0x8180 | rcode, 1, len(answers), 0, 0)
    return header + (question or query[12:]) + b''.join(answers)


class FakeDNSServer:
    """UDP server on 127.0.0.1; `handler(query) -> [datagrams]`."""

    def __init__(self, handler):
        self.handler = handler
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('127.0.0.1', 0))
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                query, addr = self.sock.recvfrom(512)
            except OSError:
                return
            for datagram in self.handler(query):
                self.sock.sendto(datagram, addr)


@pytest.fixture
def dns(env, monkeypatch):
    servers = []

    def start(handler):
        server = FakeDNSServer(handler)
        servers.append(server)
        monkeypatch.setattr(env.mod, 'DNS_PORT', server.port)
        return env.mod
    yield start
    for server in servers:
        server.sock.close()


PTR = b'\xc0\x0c'  # compression pointer to the question name


def test_a_records_and_ttl(dns):
    mod = dns(lambda q: [reply(q, [rr(PTR, 1, 300, bytes([1, 2, 3, 4])),
                                   rr(PTR, 1, 60, bytes([5, 6, 7, 8]))])])
    assert mod.dns_query('127.0.0.1', 'h.example', 'A') == (['1.2.3.4', '5.6.7.8'], 60)


def test_cname_chain(dns):
    target = name('edge.cdn.example')
    mod = dns(lambda q: [reply(q, [rr(PTR, 5, 3600, target), rr(target, 1, 20, bytes([9, 9, 9, 9]))])])
    assert mod.dns_query('127.0.0.1', 'www.example', 'A') == (['9.9.9.9'], 20)


def test_aaaa(dns):
    mod = dns(lambda q: [reply(q, [rr(PTR, 28, 30, socket.inet_pton(socket.AF_INET6, '2001:db8::1'))])])
    assert mod.dns_query('127.0.0.1', 'h.example', 'AAAA') == (['2001:db8::1'], 30)


def test_nxdomain_is_empty_not_error(dns):
    mod = dns(lambda q: [reply(q, rcode=3)])
    assert mod.dns_query('127.0.0.1', 'nope.example', 'A') == ([], None)


def test_servfail_raises(dns):
    mod = dns(lambda q: [reply(q, rcode=2)])
    with pytest.raises(mod.DNSError):
        mod.dns_query('127.0.0.1', 'h.example', 'A')


def test_wrong_id_or_question_ignored(dns):
    def handler(q):
        good = rr(PTR, 1, 60, bytes([1, 1, 1, 1]))
        spoof = rr(PTR, 1, 60, bytes([6, 6, 6, 6]))
        wrong_q = name('evil.example') + struct.pack('>HH', 1, 1)
        wrong_id = bytes([q[0] ^ 0xFF, q[1]])
        return [reply(q, [spoof], txid=wrong_id), reply(q, [spoof], question=wrong_q), reply(q, [good])]
    mod = dns(handler)
    assert mod.dns_query('127.0.0.1', 'h.example', 'A') == (['1.1.1.1'], 60)


def test_malformed_response_raises(dns):
    mod = dns(lambda q: [reply(q, [PTR + b'\x00\x01'])])  # answer cut off mid-record
    with pytest.raises(mod.DNSError):
        mod.dns_query('127.0.0.1', 'h.example', 'A')


def test_no_response_times_out(dns):
    mod = dns(lambda q: [])
    with pytest.raises(mod.DNSError):
        mod.dns_query('127.0.0.1', 'h.example', 'A', timeout=0.2)


def test_resolve_dns_uses_server_and_combines_families(dns, env):
    def handler(q):
        qtype = struct.unpack('>H', q[-4:-2])[0]
        if qtype == 1:
            return [reply(q, [rr(PTR, 1, 120, bytes([1, 2, 3, 4]))])]
        return [reply(q, [rr(PTR, 28, 40, socket.inet_pton(socket.AF_INET6, '2001:db8::5'))])]
    mod = dns(handler)
    assert mod.real_resolve_dns('h.example', 'both', dns_server='127.0.0.1') == (['1.2.3.4', '2001:db8::5'], 40)


def test_resolve_dns_server_down_returns_empty(dns):
    mod = dns(lambda q: [reply(q, rcode=2)])
    assert mod.real_resolve_dns('h.example', 'ipv4', dns_server='127.0.0.1') == ([], None)


@pytest.mark.parametrize('interval, ttl, expected', [
    (300, None, 300),   # system resolver: no TTL, plain interval
    (300, 59, 60),      # TTL expires first: check right after it does
    (30, 3600, 30),     # never later than the interval
    (300, 0, 5),        # never busier than MIN_TTL_WAIT
])
def test_next_check_delay_values(env, interval, ttl, expected):
    assert env.mod.next_check_delay({'interval': interval}, {'ttl': ttl}) == expected


def test_scheduler_uses_ttl(env, monkeypatch):
    monkeypatch.setattr(env.mod, 'resolve_dns', lambda h, af, dns_server=None: (['1.1.1.1'], 7))
    env.set_table('T')
    w = [watcher('w', 'T', hostnames='h', dnsServer='127.0.0.1', interval=3600)]
    pool = concurrent.futures.ThreadPoolExecutor(1)
    sched = env.mod.Scheduler(pool)
    start = time.time()
    deadline = start + 5
    while time.time() < deadline and env.table('T') != ['1.1.1.1']:
        sched.tick(w, 0)
        time.sleep(0.05)
    pool.shutdown()
    assert env.table('T') == ['1.1.1.1']
    assert start + 7 <= sched.next_due['w'] <= time.time() + 8
