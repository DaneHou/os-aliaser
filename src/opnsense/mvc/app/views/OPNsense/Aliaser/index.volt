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
                            return '<span class="fa fa-fw fa-globe"></span> ' + row.hostname;
                        } else {
                            return '<span class="fa fa-fw fa-link"></span> ' + row.url;
                        }
                    },
                    "intervalFmt": function(column, row) {
                        return row.interval + 's';
                    }
                }
            }
        });

        // Toggle DNS/URL fields based on type
        $(document).on('change', '#watcher\\.type', function() {
            var wtype = $(this).val();
            if (wtype === 'dns') {
                $('#row_watcher\\.hostname').show();
                $('#row_watcher\\.url').hide();
                $('#row_watcher\\.addressFamily').show();
            } else {
                $('#row_watcher\\.hostname').hide();
                $('#row_watcher\\.url').show();
                $('#row_watcher\\.addressFamily').hide();
            }
        });

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
                <th data-column-id="enabled" data-width="5em" data-type="string" data-formatter="status">{{ lang._('Enabled') }}</th>
                <th data-column-id="name" data-type="string">{{ lang._('Name') }}</th>
                <th data-column-id="type" data-width="8em" data-type="string">{{ lang._('Type') }}</th>
                <th data-column-id="hostname" data-type="string" data-formatter="watcherTarget">{{ lang._('Target') }}</th>
                <th data-column-id="alias" data-type="string">{{ lang._('Alias') }}</th>
                <th data-column-id="interval" data-width="7em" data-type="string" data-formatter="intervalFmt">{{ lang._('Interval') }}</th>
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
