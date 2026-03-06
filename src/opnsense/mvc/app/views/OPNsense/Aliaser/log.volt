{#
  OPNsense Aliaser — Log Viewer
  Services > Aliaser > Log
#}

<script>
    $(document).ready(function() {
        ajaxGet('/api/diagnostics/log/core/syslog', { 'severity': '', 'limit': 500, 'module': 'aliaserd' }, function(data) {
            var tbody = $('#aliaser-log-table tbody');
            tbody.empty();
            if (data && data.rows) {
                $.each(data.rows, function(idx, row) {
                    tbody.append(
                        '<tr><td>' + row.timestamp + '</td>' +
                        '<td>' + row.process_name + '</td>' +
                        '<td>' + row.line + '</td></tr>'
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
