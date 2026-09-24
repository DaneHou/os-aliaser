{#
  OPNsense Aliaser — Log Viewer
  Services > Aliaser > Log
#}

<script>
    // Everything below comes from config, the daemon, or remote feeds/logs:
    // escape it before building HTML strings.
    function esc(s) {
        return $('<div>').text(s == null ? '' : String(s)).html().replace(/"/g, '&quot;');
    }

    $(document).ready(function() {
        ajaxGet('/api/diagnostics/log/core/syslog', { 'severity': '', 'limit': 500, 'module': 'core', 'filename': 'system', 'filter': 'aliaserd' }, function(data) {
            var tbody = $('#aliaser-log-table tbody');
            tbody.empty();
            if (data && data.rows) {
                $.each(data.rows, function(idx, row) {
                    // The API filter is a plain text match, so it also returns lines
                    // from other processes that merely mention "aliaserd".
                    if (row.process_name !== 'aliaserd') {
                        return;
                    }
                    tbody.append(
                        '<tr><td>' + esc(row.timestamp) + '</td>' +
                        '<td>' + esc(row.process_name) + '</td>' +
                        '<td>' + esc(row.line) + '</td></tr>'
                    );
                });
            }
            if (tbody.children().length === 0) {
                tbody.append('<tr><td colspan="3" class="text-center text-muted">No log entries found. The daemon logs to syslog facility "aliaserd".</td></tr>');
            }
        });
    });
</script>

<div class="content-box">
    <div class="content-box-header">
        <h3>{{ lang._('Aliaser Log') }}</h3>
    </div>
    <div class="content-box-main">
        <div class="table-responsive">
            <table id="aliaser-log-table" class="table table-condensed table-hover table-striped">
                <thead>
                    <tr>
                        <th style="width:180px;">{{ lang._('Time') }}</th>
                        <th style="width:120px;">{{ lang._('Process') }}</th>
                        <th>{{ lang._('Message') }}</th>
                    </tr>
                </thead>
                <tbody>
                    <tr><td colspan="3" class="text-center"><span class="fa fa-spinner fa-spin"></span> Loading...</td></tr>
                </tbody>
            </table>
        </div>
    </div>
</div>
