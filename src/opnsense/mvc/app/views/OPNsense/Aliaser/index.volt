{#
  OPNsense Aliaser — Watcher Configuration Page
  Services > Aliaser > Watchers
#}

<style>
    .alias-picker-row {
        margin-top: 5px;
    }
    .alias-picker-row .btn {
        margin-right: 5px;
        margin-bottom: 3px;
    }
    .alias-picker-row .btn .badge {
        margin-left: 4px;
        background: rgba(0,0,0,0.15);
    }
    .alias-external { border-color: #5cb85c; }
    .alias-host { border-color: #5bc0de; }
    .alias-other { border-color: #777; }
</style>

<script>
    $( document ).ready(function() {
        // Load general settings
        mapDataToFormUI({'frm_GeneralSettings': "/api/aliaser/settings/get"}).done(function(){
            formatTokenizersUI();
            $('.selectpicker').selectpicker('refresh');
        });

        // Watcher grid
        $("#grid-watchers").UIBootgrid({
            search: '/api/aliaser/watcher/searchWatcher',
            get: '/api/aliaser/watcher/getWatcher/',
            set: '/api/aliaser/watcher/setWatcher/',
            add: '/api/aliaser/watcher/addWatcher/',
            del: '/api/aliaser/watcher/delWatcher/',
            options: {
                formatters: {
                    "commands": function(column, row) {
                        return '<button type="button" class="btn btn-xs btn-default command-edit bootgrid-tooltip" ' +
                            'data-row-id="' + row.uuid + '"><span class="fa fa-fw fa-pencil"></span></button> ' +
                            '<button type="button" class="btn btn-xs btn-default command-delete bootgrid-tooltip" ' +
                            'data-row-id="' + row.uuid + '"><span class="fa fa-fw fa-trash-o"></span></button>';
                    },
                    "status": function(column, row) {
                        if (row.enabled == "1") {
                            return '<span class="fa fa-fw fa-check-circle text-success"></span>';
                        } else {
                            return '<span class="fa fa-fw fa-times-circle text-danger"></span>';
                        }
                    },
                    "watcherTarget": function(column, row) {
                        if (row.type === 'dns') {
                            return '<span class="fa fa-fw fa-globe text-primary"></span> ' + (row.hostname || '-');
                        } else {
                            return '<span class="fa fa-fw fa-link text-info"></span> ' + (row.url || '-');
                        }
                    },
                    "typeBadge": function(column, row) {
                        if (row.type === 'dns') {
                            return '<span class="label label-primary">DNS</span>';
                        } else {
                            return '<span class="label label-info">URL</span>';
                        }
                    },
                    "intervalFmt": function(column, row) {
                        var s = parseInt(row.interval);
                        if (s >= 3600) return Math.floor(s/3600) + 'h';
                        if (s >= 60) return Math.floor(s/60) + 'm';
                        return s + 's';
                    }
                }
            }
        });

        // When watcher dialog opens, add alias picker and toggle fields
        $(document).on('opendialog.DialogWatcher', function(e) {
            toggleTypeFields();
            loadAliasPicker();
        });

        // Toggle DNS/URL fields based on type
        function toggleTypeFields() {
            var wtype = $('#watcher\\.type').val();
            if (wtype === 'dns') {
                $('[id="row_watcher.hostname"]').show();
                $('[id="row_watcher.url"]').hide();
                $('[id="row_watcher.addressFamily"]').show();
            } else {
                $('[id="row_watcher.hostname"]').hide();
                $('[id="row_watcher.url"]').show();
                $('[id="row_watcher.addressFamily"]').hide();
            }
        }
        $(document).on('change', '#watcher\\.type', toggleTypeFields);

        // Load alias picker buttons below the alias text field
        function loadAliasPicker() {
            // Remove old picker
            $('#alias-picker-container').remove();

            var aliasInput = $('#watcher\\.alias');
            var container = $('<div id="alias-picker-container" class="alias-picker-row"></div>');
            container.append('<small class="text-muted">Click to select — </small>');

            $.get('/api/aliaser/status/aliases', function(response) {
                if (!response || !response.aliases || response.aliases.length === 0) {
                    container.append('<small class="text-muted">No aliases found. Create one in Firewall > Aliases (type: External).</small>');
                } else {
                    // Show external aliases first, then others
                    var sorted = response.aliases.sort(function(a, b) {
                        if (a.type === 'external' && b.type !== 'external') return -1;
                        if (a.type !== 'external' && b.type === 'external') return 1;
                        return a.name.localeCompare(b.name);
                    });

                    $.each(sorted, function(idx, a) {
                        var btnClass = 'btn-default alias-other';
                        var typeLabel = a.type;
                        if (a.type === 'external') {
                            btnClass = 'btn-success alias-external';
                            typeLabel = 'external';
                        } else if (a.type === 'host') {
                            btnClass = 'btn-info alias-host';
                            typeLabel = 'host';
                        }

                        var btn = $('<button type="button" class="btn btn-xs ' + btnClass + '"></button>');
                        btn.text(a.name);
                        btn.append(' <span class="badge">' + typeLabel + '</span>');
                        if (a.entry_count > 0) {
                            btn.append(' <span class="badge">' + a.entry_count + ' IPs</span>');
                        }
                        if (a.type !== 'external') {
                            btn.attr('title', 'Warning: non-External aliases are also managed by OPNsense. Use External type to avoid conflicts.');
                        }
                        btn.on('click', function() {
                            aliasInput.val(a.name).trigger('change');
                            container.find('.btn').removeClass('active');
                            $(this).addClass('active');
                        });
                        container.append(btn);
                    });
                }

                // "Create new" button
                var createBtn = $('<button type="button" class="btn btn-xs btn-warning"><span class="fa fa-plus"></span> New External Alias</button>');
                createBtn.on('click', function() {
                    var newName = prompt('Enter alias name (alphanumeric + underscores, max 31 chars):');
                    if (newName && /^[a-zA-Z0-9_]{1,31}$/.test(newName)) {
                        $.post('/api/aliaser/status/createAlias', {name: newName}, function(resp) {
                            if (resp && resp.status === 'ok') {
                                aliasInput.val(newName).trigger('change');
                                loadAliasPicker(); // Reload to show new alias
                            } else {
                                alert('Failed: ' + (resp.message || 'unknown error'));
                            }
                        });
                    } else if (newName) {
                        alert('Invalid name. Use 1-31 alphanumeric characters or underscores.');
                    }
                });
                container.append(createBtn);

                // Highlight currently selected alias
                var currentVal = aliasInput.val();
                if (currentVal) {
                    container.find('.btn').each(function() {
                        if ($(this).text().indexOf(currentVal) === 0) {
                            $(this).addClass('active');
                        }
                    });
                }

                aliasInput.closest('td').append(container);
            });
        }

        // Reconfigure (apply changes)
        $("#reconfigureAct").SimpleActionButton({
            onPreAction: function() {
                const dfObj = new $.Deferred();
                saveFormToEndpoint("/api/aliaser/settings/set", 'frm_GeneralSettings',
                    function() { dfObj.resolve(); },
                    true,
                    function() { dfObj.reject(); }
                );
                return dfObj;
            },
            onAction: function(data, status) {
                updateServiceControlUI('aliaser');
                $('#grid-watchers').bootgrid('reload');
            }
        });

        updateServiceControlUI('aliaser');
    });
</script>

<div class="tab-content content-box">
    <div id="general" class="tab-pane fade in active">
        <div class="content-box" style="padding-bottom: 1.5em;">
            {{ partial("layout_partials/base_form",['fields':generalForm,'id':'frm_GeneralSettings'])}}
        </div>
    </div>
</div>

<!-- Watchers Grid -->
<div class="tab-content content-box">
    <table id="grid-watchers" class="table table-condensed table-hover table-striped"
           data-editDialog="DialogWatcher"
           data-editAlert="WatcherChangeMessage">
        <thead>
            <tr>
                <th data-column-id="uuid" data-type="string" data-identifier="true" data-visible="false">ID</th>
                <th data-column-id="enabled" data-width="5em" data-type="string" data-formatter="status">{{ lang._('On') }}</th>
                <th data-column-id="name" data-type="string" data-width="10em">{{ lang._('Name') }}</th>
                <th data-column-id="type" data-width="5em" data-type="string" data-formatter="typeBadge">{{ lang._('Type') }}</th>
                <th data-column-id="hostname" data-type="string" data-formatter="watcherTarget">{{ lang._('Target') }}</th>
                <th data-column-id="alias" data-type="string" data-width="12em">{{ lang._('Alias') }}</th>
                <th data-column-id="interval" data-width="6em" data-type="string" data-formatter="intervalFmt">{{ lang._('Interval') }}</th>
                <th data-column-id="description" data-type="string">{{ lang._('Description') }}</th>
                <th data-column-id="commands" data-width="7em" data-formatter="commands"
                    data-sortable="false">{{ lang._('Commands') }}</th>
            </tr>
        </thead>
        <tbody>
        </tbody>
        <tfoot>
            <tr>
                <td></td>
                <td>
                    <button data-action="add" type="button" class="btn btn-xs btn-primary">
                        <span class="fa fa-fw fa-plus"></span>
                    </button>
                    <button data-action="deleteSelected" type="button" class="btn btn-xs btn-default">
                        <span class="fa fa-fw fa-trash-o"></span>
                    </button>
                </td>
            </tr>
        </tfoot>
    </table>
</div>

<div class="col-md-12">
    <div id="WatcherChangeMessage" class="alert alert-info" style="display: none" role="alert">
        {{ lang._('After changing settings, please remember to apply them.') }}
    </div>
    <hr/>
    <button class="btn btn-primary" id="reconfigureAct"
            data-endpoint='/api/aliaser/service/reconfigure'
            data-label="{{ lang._('Apply') }}"
            data-error-title="{{ lang._('Error reconfiguring Aliaser') }}"
            type="button">
    </button>
</div>

{# Watcher Edit Dialog #}
{{ partial("layout_partials/base_dialog",['fields':watcherForm,'id':'DialogWatcher','label':lang._('Edit Watcher')]) }}
