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

use OPNsense\Base\ApiMutableModelControllerBase;

/**
 * CRUD controller for watcher entries.
 *
 * Endpoints:
 *   GET    /api/aliaser/watcher/searchWatcher
 *   GET    /api/aliaser/watcher/getWatcher/{uuid}
 *   POST   /api/aliaser/watcher/addWatcher
 *   POST   /api/aliaser/watcher/setWatcher/{uuid}
 *   POST   /api/aliaser/watcher/delWatcher/{uuid}
 */
class WatcherController extends ApiMutableModelControllerBase
{
    protected static $internalModelName = 'Aliaser';
    protected static $internalModelClass = 'OPNsense\Aliaser\Aliaser';

    public function searchWatcherAction()
    {
        return $this->searchBase(
            'watchers.watcher',
            ['enabled', 'name', 'type', 'hostname', 'hostnames', 'url', 'staticEntries', 'includeAliases', 'alias', 'interval', 'description'],
            'name'
        );
    }

    public function getWatcherAction($uuid = null)
    {
        return $this->getBase('watcher', 'watchers.watcher', $uuid);
    }

    public function addWatcherAction()
    {
        return $this->addBase('watcher', 'watchers.watcher');
    }

    public function setWatcherAction($uuid)
    {
        return $this->setBase('watcher', 'watchers.watcher', $uuid);
    }

    public function delWatcherAction($uuid)
    {
        return $this->delBase('watchers.watcher', $uuid);
    }
}
