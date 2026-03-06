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

use OPNsense\Base\ApiMutableServiceControllerBase;

/**
 * Service lifecycle controller.
 *
 * Endpoints:
 *   POST /api/aliaser/service/start
 *   POST /api/aliaser/service/stop
 *   POST /api/aliaser/service/restart
 *   POST /api/aliaser/service/reconfigure
 *   GET  /api/aliaser/service/status
 */
class ServiceController extends ApiMutableServiceControllerBase
{
    protected static $internalServiceClass = '\OPNsense\Aliaser\Aliaser';
    protected static $internalServiceEnabled = 'general.enabled';
    protected static $internalServiceName = 'aliaser';

    public function reconfigureAction()
    {
        $result = ['status' => 'failed'];

        if ($this->request->isPost()) {
            session_write_close();

            $backend = new \OPNsense\Core\Backend();
            $response = trim($backend->configdpRun('aliaser reconfigure'));
            $result = ['status' => 'ok', 'response' => $response];
        }

        return $result;
    }
}
