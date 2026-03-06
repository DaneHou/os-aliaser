{#
  OPNsense Aliaser — Status Dashboard
  Services > Aliaser > Status
#}

<style>
    .aliaser-card {
        border: 1px solid #ddd;
        border-radius: 4px;
        padding: 15px;
        margin-bottom: 15px;
        background: #fff;
    }
    .aliaser-card.has-error {
        border-color: #d9534f;
    }
    .aliaser-card .card-header {
        font-size: 16px;
        font-weight: bold;
        margin-bottom: 10px;
    }
    .aliaser-metric {
        display: inline-block;
        margin-right: 20px;
        color: #666;
    }
    .aliaser-metric .value {
        font-weight: bold;
        color: #333;
    }
    .aliaser-ips {
        margin-top: 10px;
        padding: 8px;
        background: #f5f5f5;
        border-radius: 3px;
        font-family: monospace;
        font-size: 12px;
        max-height: 150px;
        overflow-y: auto;
    }
</style>

<script>
    function formatTimestamp(ts) {
        if (!ts || ts === 0) return 'Never';
        var d = new Date(ts * 1000);
        return d.toLocaleString();
    }

    function loadStatus() {
        $.get('/api/aliaser/status/get', function(response) {
            var container = $('#aliaser-status-container');
            container.empty();

            if (!response || !response.watchers || Object.keys(response.watchers).length === 0) {
                container.html('<div class="alert alert-info">No watchers configured or daemon not running.</div>');
                return;
            }

            // Daemon status
            if (response.status === 'ok' && response.watchers) {
                $.each(response.watchers, function(name, w) {
                    var hasError = w.consecutive_errors > 0;
                    var card = $('<div class="aliaser-card' + (hasError ? ' has-error' : '') + '"></div>');

                    var header = '<div class="card-header">' +
                        '<span class="fa fa-fw ' + (w.type === 'dns' ? 'fa-globe' : 'fa-link') + '"></span> ' +
                        name +
                        ' <small class="text-muted">(' + w.alias + ')</small>' +
                        '<button class="btn btn-xs btn-default pull-right btn-refresh" data-uuid="' + w.uuid + '">' +
                        '<span class="fa fa-refresh"></span> Refresh Now</button>' +
                        '</div>';
                    card.append(header);

                    var metrics = '<div>' +
                        '<span class="aliaser-metric">Target: <span class="value">' + (w.target || '-') + '</span></span>' +
                        '<span class="aliaser-metric">IPs: <span class="value">' + w.ip_count + '</span></span>' +
                        '<span class="aliaser-metric">Interval: <span class="value">' + w.interval + 's</span></span>' +
                        '<span class="aliaser-metric">Last Check: <span class="value">' + formatTimestamp(w.last_check) + '</span></span>' +
                        '<span class="aliaser-metric">Last Change: <span class="value">' + formatTimestamp(w.last_change) + '</span></span>';

                    if (hasError) {
                        metrics += '<span class="aliaser-metric text-danger">Errors: <span class="value">' +
                            w.consecutive_errors + '</span></span>' +
                            '<br/><span class="text-danger"><small>' + w.last_error + '</small></span>';
                    }
                    metrics += '</div>';
                    card.append(metrics);

                    if (w.current_ips && w.current_ips.length > 0) {
                        var ipList = '<div class="aliaser-ips">' + w.current_ips.join('<br/>') + '</div>';
                        card.append(ipList);
                    }

                    container.append(card);
                });
            }
        });
    }

    $(document).ready(function() {
        loadStatus();
        // Auto-refresh every 10 seconds
        setInterval(loadStatus, 10000);

        // Manual refresh button
        $(document).on('click', '.btn-refresh', function() {
            var uuid = $(this).data('uuid');
            var btn = $(this);
            btn.prop('disabled', true);
            $.post('/api/aliaser/status/refresh/' + uuid, function() {
                setTimeout(function() {
                    loadStatus();
                    btn.prop('disabled', false);
                }, 1000);
            });
        });
    });
</script>

<div class="content-box">
    <div class="content-box-header">
        <h3>{{ lang._('Aliaser Status') }}</h3>
    </div>
    <div class="content-box-main">
        <div id="aliaser-status-container">
            <div class="text-center"><span class="fa fa-spinner fa-spin"></span> Loading...</div>
        </div>
    </div>
</div>
