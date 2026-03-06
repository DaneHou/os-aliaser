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

namespace OPNsense\Aliaser\Api;

use OPNsense\Base\ApiControllerBase;

/**
 * Status and diagnostics API.
 *
 * Endpoints:
 *   GET  /api/aliaser/status/get          -- all watcher statuses
 *   POST /api/aliaser/status/refresh/{uuid} -- force immediate refresh
 */
class StatusController extends ApiControllerBase
{
    public function getAction()
    {
        $backend = new \OPNsense\Core\Backend();
        $response = $backend->configdpRun('aliaser status');
        $data = json_decode(trim($response), true);
        return ['status' => 'ok', 'watchers' => $data ?: []];
    }

    public function refreshAction($uuid = null)
    {
        $result = ['status' => 'failed'];

        if ($this->request->isPost() && !empty($uuid)) {
            $backend = new \OPNsense\Core\Backend();
            $response = trim($backend->configdpRun("aliaser refresh {$uuid}"));
            $result = ['status' => 'ok', 'response' => $response];
        }

        return $result;
    }
}
