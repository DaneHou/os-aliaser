{#
  OPNsense Aliaser — Watcher Configuration Page
  Services > Aliaser > Watchers
#}

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
                            '<button type="button" class="btn btn-xs btn-default command-copy bootgrid-tooltip" ' +
                            'data-row-id="' + row.uuid + '"><span class="fa fa-fw fa-clone"></span></button> ' +
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

        // Populate alias dropdown when edit dialog opens
        $(document).on('opendialog.DialogWatcher', function(e) {
            var aliasSelect = $('#watcher\\.alias');
            var currentVal = aliasSelect.val();

            $.get('/api/aliaser/status/aliases', function(response) {
                if (response && response.aliases) {
                    aliasSelect.empty();
                    aliasSelect.append('<option value="">-- Select an alias --</option>');
                    $.each(response.aliases, function(idx, a) {
                        var label = a.name;
                        if (a.type) label += ' (' + a.type + ')';
                        if (a.description) label += ' - ' + a.description;
                        if (a.entry_count > 0) label += ' [' + a.entry_count + ' IPs]';
                        var opt = $('<option></option>').val(a.name).text(label);
                        aliasSelect.append(opt);
                    });
                    // Add option to type a custom name (for new aliases)
                    aliasSelect.append('<option value="__new__">+ Create new alias...</option>');

                    // Restore current value
                    if (currentVal) {
                        if (aliasSelect.find('option[value="' + currentVal + '"]').length > 0) {
                            aliasSelect.val(currentVal);
                        } else {
                            // Current value is a custom name not in the list
                            aliasSelect.prepend('<option value="' + currentVal + '">' + currentVal + ' (custom)</option>');
                            aliasSelect.val(currentVal);
                        }
                    }
                    aliasSelect.selectpicker('refresh');
                }
            });

            // Toggle fields based on type
            toggleTypeFields();
        });

        // Handle "Create new alias" selection
        $(document).on('change', '#watcher\\.alias', function() {
            if ($(this).val() === '__new__') {
                BootstrapDialog.show({
                    title: '{{ lang._("Create New Alias") }}',
                    message: '<div class="form-group">' +
                        '<label>Alias Name</label>' +
                        '<input type="text" class="form-control" id="newAliasName" ' +
                        'placeholder="e.g. My_Remote_IPs" pattern="[a-zA-Z0-9_]{1,31}">' +
                        '<small class="text-muted">Alphanumeric + underscores, max 31 chars. ' +
                        'An External-type alias will be created in OPNsense.</small>' +
                        '</div>',
                    buttons: [{
                        label: '{{ lang._("Create") }}',
                        cssClass: 'btn-primary',
                        action: function(dialog) {
                            var newName = dialog.getModalBody().find('#newAliasName').val().trim();
                            if (newName && /^[a-zA-Z0-9_]{1,31}$/.test(newName)) {
                                // Create the alias via API
                                $.post('/api/aliaser/status/createAlias', {name: newName}, function(resp) {
                                    if (resp && resp.status === 'ok') {
                                        var aliasSelect = $('#watcher\\.alias');
                                        aliasSelect.find('option[value="__new__"]').before(
                                            '<option value="' + newName + '">' + newName + ' (external)</option>'
                                        );
                                        aliasSelect.val(newName);
                                        aliasSelect.selectpicker('refresh');
                                    } else {
                                        alert('Failed to create alias: ' + (resp.message || 'unknown error'));
                                    }
                                });
                                dialog.close();
                            } else {
                                alert('Invalid name. Use 1-31 alphanumeric characters or underscores.');
                            }
                        }
                    }, {
                        label: '{{ lang._("Cancel") }}',
                        action: function(dialog) {
                            $('#watcher\\.alias').val('');
                            $('#watcher\\.alias').selectpicker('refresh');
                            dialog.close();
                        }
                    }]
                });
            }
        });

        // Toggle DNS/URL fields based on type
        function toggleTypeFields() {
            var wtype = $('#watcher\\.type').val();
            if (wtype === 'dns') {
                $('#row_watcher\\.hostname').show();
                $('#row_watcher\\.url').hide();
                $('#row_watcher\\.addressFamily').show();
            } else {
                $('#row_watcher\\.hostname').hide();
                $('#row_watcher\\.url').show();
                $('#row_watcher\\.addressFamily').hide();
            }
        }
        $(document).on('change', '#watcher\\.type', toggleTypeFields);

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
                <th data-column-id="commands" data-width="10em" data-formatter="commands"
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
