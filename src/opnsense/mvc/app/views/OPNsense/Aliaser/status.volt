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
        border-left: 4px solid #d9534f;
    }
    .aliaser-card.healthy {
        border-left: 4px solid #5cb85c;
    }
    .aliaser-card.stale {
        border-left: 4px solid #f0ad4e;
    }
    .card-title {
        font-size: 16px;
        font-weight: bold;
        margin-bottom: 12px;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    .card-title .left {
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .metrics-row {
        display: flex;
        flex-wrap: wrap;
        gap: 20px;
        margin-bottom: 10px;
    }
    .metric {
        font-size: 13px;
    }
    .metric .label-text {
        color: #888;
    }
    .metric .value {
        font-weight: 600;
        color: #333;
    }
    .ip-table {
        margin-top: 10px;
        background: #f8f8f8;
        border: 1px solid #eee;
        border-radius: 3px;
        max-height: 200px;
        overflow-y: auto;
    }
    .ip-table table {
        margin: 0;
        font-size: 12px;
    }
    .ip-table table td {
        padding: 3px 10px;
        font-family: monospace;
    }
    .daemon-bar {
        padding: 10px 15px;
        margin-bottom: 15px;
        border-radius: 4px;
        font-size: 13px;
    }
    .daemon-bar.running { background: #dff0d8; border: 1px solid #d6e9c6; }
    .daemon-bar.stopped { background: #f2dede; border: 1px solid #ebccd1; }
    .alert-badge-empty { background: #d9534f; color: #fff; padding: 2px 8px; border-radius: 3px; font-size: 11px; margin-left: 5px; }
    .alert-badge-threshold { background: #f0ad4e; color: #fff; padding: 2px 8px; border-radius: 3px; font-size: 11px; margin-left: 5px; }
    .sources-list { font-size: 12px; color: #666; margin-bottom: 8px; }
    .sources-list span { margin-right: 12px; }
    .history-panel { margin-top: 10px; font-size: 12px; }
    .history-panel summary { cursor: pointer; color: #337ab7; font-weight: 600; }
    .history-entry { padding: 4px 0; border-bottom: 1px solid #eee; }
    .history-entry .added { color: #5cb85c; }
    .history-entry .removed { color: #d9534f; }
</style>

<script>
    function timeAgo(ts) {
        if (!ts || ts === 0) return 'Never';
        var now = Math.floor(Date.now() / 1000);
        var diff = now - ts;
        if (diff < 5) return 'Just now';
        if (diff < 60) return diff + 's ago';
        if (diff < 3600) return Math.floor(diff/60) + 'm ago';
        if (diff < 86400) return Math.floor(diff/3600) + 'h ago';
        return Math.floor(diff/86400) + 'd ago';
    }

    function formatTime(ts) {
        if (!ts || ts === 0) return '-';
        return new Date(ts * 1000).toLocaleString();
    }

    function loadStatus() {
        $.get('/api/aliaser/status/get', function(response) {
            var container = $('#aliaser-watchers');

            if (!response || response.status !== 'ok' || !response.watchers || !response.watchers.watchers) {
                container.html('<div class="alert alert-warning">Unable to load status. Is the daemon running?</div>');
                return;
            }

            var data = response.watchers;

            // Daemon status bar
            var daemonBar = $('#daemon-status');
            if (data.daemon && data.daemon.running) {
                daemonBar.attr('class', 'daemon-bar running');
                daemonBar.html('<span class="fa fa-check-circle text-success"></span> Daemon running (PID ' + data.daemon.pid + ')');
            } else {
                daemonBar.attr('class', 'daemon-bar stopped');
                daemonBar.html('<span class="fa fa-times-circle text-danger"></span> Daemon not running');
            }

            container.empty();

            if (!data.watchers || Object.keys(data.watchers).length === 0) {
                container.html('<div class="alert alert-info">No watchers configured. Go to Watchers tab to add one.</div>');
                return;
            }

            $.each(data.watchers, function(name, w) {
                var hasError = w.consecutive_errors > 0;
                var isStale = w.last_check > 0 && (Date.now()/1000 - w.last_check) > w.interval * 3;
                var cardClass = hasError ? 'has-error' : (isStale ? 'stale' : 'healthy');

                var html = '<div class="aliaser-card ' + cardClass + '">';

                // Title row
                html += '<div class="card-title">';
                html += '<div class="left">';
                var icon = w.type === 'dns' ? 'fa-globe text-primary' : 'fa-link text-info';
                html += '<span class="fa ' + icon + '"></span>';
                html += '<span>' + name + '</span>';
                html += '<span class="label label-' + (w.type === 'dns' ? 'primary' : 'info') + '">' + w.type.toUpperCase() + '</span>';
                if (hasError) {
                    html += '<span class="label label-danger">' + w.consecutive_errors + ' errors</span>';
                }
                // Health alerts
                if (w.alerts) {
                    $.each(w.alerts, function(i, alert) {
                        if (alert.type === 'empty') {
                            html += '<span class="alert-badge-empty"><span class="fa fa-exclamation-circle"></span> ' + alert.message + '</span>';
                        } else if (alert.type === 'threshold') {
                            html += '<span class="alert-badge-threshold"><span class="fa fa-warning"></span> ' + alert.message + '</span>';
                        }
                    });
                }
                html += '</div>';
                html += '<button class="btn btn-xs btn-default btn-refresh" data-uuid="' + w.uuid + '">' +
                    '<span class="fa fa-refresh"></span> Refresh Now</button>';
                html += '</div>';

                // Sources summary (composite)
                if (w.sources && w.sources.length > 0) {
                    html += '<div class="sources-list">';
                    $.each(w.sources, function(i, src) {
                        html += '<span><span class="fa fa-fw fa-angle-right"></span> ' + src + '</span>';
                    });
                    html += '</div>';
                }

                // Metrics
                html += '<div class="metrics-row">';
                html += '<div class="metric"><span class="label-text">Alias:</span> <span class="value">' + w.alias + '</span></div>';
                html += '<div class="metric"><span class="label-text">IPs in table:</span> <span class="value">' + w.ip_count + '</span></div>';
                html += '<div class="metric"><span class="label-text">Interval:</span> <span class="value">' + w.interval + 's</span></div>';
                html += '<div class="metric"><span class="label-text">Last checked:</span> <span class="value" title="' + formatTime(w.last_check) + '">' + timeAgo(w.last_check) + '</span></div>';
                html += '<div class="metric"><span class="label-text">Last changed:</span> <span class="value" title="' + formatTime(w.last_change) + '">' + timeAgo(w.last_change) + '</span></div>';
                html += '</div>';

                // Error message
                if (hasError && w.last_error) {
                    html += '<div class="text-danger" style="margin-bottom:8px;font-size:12px;">' +
                        '<span class="fa fa-exclamation-triangle"></span> ' + w.last_error + '</div>';
                }

                // IP table
                if (w.current_ips && w.current_ips.length > 0) {
                    html += '<div class="ip-table"><table class="table table-condensed">';
                    $.each(w.current_ips, function(i, ip) {
                        html += '<tr><td style="width:30px;color:#999;">' + (i+1) + '</td><td>' + ip + '</td></tr>';
                    });
                    html += '</table></div>';
                } else {
                    html += '<div class="text-muted" style="font-size:12px;margin-top:5px;">' +
                        '<span class="fa fa-info-circle"></span> No IPs in table</div>';
                }

                // Change history
                if (w.history && w.history.length > 0) {
                    html += '<div class="history-panel"><details>';
                    html += '<summary><span class="fa fa-history"></span> Change History (' + w.history.length + ')</summary>';
                    // Show newest first
                    var hist = w.history.slice().reverse();
                    $.each(hist, function(i, h) {
                        html += '<div class="history-entry">';
                        html += '<span class="text-muted">' + formatTime(h.timestamp) + '</span> ';
                        html += h.old_count + ' &rarr; ' + h.new_count + ' entries';
                        if (h.added && h.added.length > 0) {
                            html += ' <span class="added">+' + h.added.length + ' added</span>';
                            html += ' <small class="text-muted">(' + h.added.slice(0, 5).join(', ');
                            if (h.added.length > 5) html += '...';
                            html += ')</small>';
                        }
                        if (h.removed && h.removed.length > 0) {
                            html += ' <span class="removed">-' + h.removed.length + ' removed</span>';
                            html += ' <small class="text-muted">(' + h.removed.slice(0, 5).join(', ');
                            if (h.removed.length > 5) html += '...';
                            html += ')</small>';
                        }
                        html += '</div>';
                    });
                    html += '</details></div>';
                }

                html += '</div>';
                container.append(html);
            });
        });
    }

    $(document).ready(function() {
        loadStatus();
        setInterval(loadStatus, 10000);

        $(document).on('click', '.btn-refresh', function() {
            var uuid = $(this).data('uuid');
            var btn = $(this);
            btn.prop('disabled', true).find('.fa').addClass('fa-spin');
            $.post('/api/aliaser/status/refresh/' + uuid, function() {
                setTimeout(function() {
                    loadStatus();
                    btn.prop('disabled', false).find('.fa').removeClass('fa-spin');
                }, 1500);
            });
        });
    });
</script>

<div class="content-box">
    <div id="daemon-status" class="daemon-bar stopped">
        <span class="fa fa-spinner fa-spin"></span> Loading...
    </div>
    <div id="aliaser-watchers">
        <div class="text-center" style="padding:30px;">
            <span class="fa fa-spinner fa-spin fa-2x"></span>
        </div>
    </div>
</div>
