<?php

/*
 * Copyright (c) 2024-2026 DaneHou
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 * 1. Redistributions of source code must retain the above copyright notice,
 *    this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright notice,
 *    this list of conditions and the following disclaimer in the documentation
 *    and/or other materials provided with the distribution.
 *
 * THIS SOFTWARE IS PROVIDED "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
 * INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY
 * AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
 */

function aliaser_enabled()
{
    return (string)(new \OPNsense\Aliaser\Aliaser())->general->enabled == '1';
}

/**
 * Register the aliaser daemon with OPNsense service manager.
 */
function aliaser_services()
{
    $services = [];

    if (!aliaser_enabled()) {
        return $services;
    }

    $services[] = [
        'description' => 'Aliaser Daemon',
        'configd' => [
            'start'   => ['aliaser start'],
            'restart' => ['aliaser restart'],
            'stop'    => ['aliaser stop'],
        ],
        'name' => 'aliaser',
        'pidfile' => '/var/run/aliaser.pid',
    ];

    return $services;
}

/**
 * Boot handler: start the daemon if enabled.
 */
function aliaser_configure()
{
    return [
        'bootup' => ['aliaser_boot:3'],
    ];
}

function aliaser_boot($verbose = false)
{
    if (!aliaser_enabled()) {
        return;
    }

    service_log('Starting Aliaser daemon...', $verbose);
    configd_run('aliaser start');
    service_log("done.\n", $verbose);
}

/**
 * Register syslog target.
 */
function aliaser_syslog()
{
    return [
        'aliaser' => ['facility' => ['aliaser']],
    ];
}

/**
 * HA sync metadata.
 */
function aliaser_xmlrpc_sync()
{
    return [[
        'id'          => 'aliaser',
        'section'     => 'OPNsense.Aliaser',
        'description' => gettext('Aliaser'),
        'services'    => ['aliaser'],
    ]];
}
