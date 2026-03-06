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
use OPNsense\Core\Config;

/**
 * Status and diagnostics API.
 *
 * Endpoints:
 *   GET  /api/aliaser/status/get            -- all watcher statuses
 *   POST /api/aliaser/status/refresh/{uuid}  -- force immediate refresh
 *   GET  /api/aliaser/status/aliases         -- list existing OPNsense aliases
 *   POST /api/aliaser/status/createAlias     -- create new External-type alias
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

    /**
     * List all existing OPNsense firewall aliases.
     * Returns name, type, description, and current entry count for each.
     * Used to populate the alias dropdown in the watcher edit dialog.
     */
    public function aliasesAction()
    {
        $aliases = [];
        $configObj = Config::getInstance();
        $xml = $configObj->object();

        if (isset($xml->OPNsense->Firewall->Alias->aliases)) {
            foreach ($xml->OPNsense->Firewall->Alias->aliases->children() as $alias) {
                if ($alias->getName() !== 'alias') {
                    continue;
                }
                $name = (string)$alias->name;
                $type = (string)$alias->type;
                $descr = (string)$alias->description;

                // Get current pf table entry count
                $count = 0;
                $output = [];
                exec("/sbin/pfctl -t " . escapeshellarg($name) . " -T show 2>/dev/null", $output);
                $count = count(array_filter($output, function ($line) {
                    return trim($line) !== '';
                }));

                $aliases[] = [
                    'name' => $name,
                    'type' => $type,
                    'description' => $descr,
                    'entry_count' => $count,
                ];
            }
        }

        return ['status' => 'ok', 'aliases' => $aliases];
    }

    /**
     * Create a new External (Advanced) alias in OPNsense.
     * External aliases are designed for management by external scripts,
     * which is exactly what the aliaser daemon does.
     */
    public function createAliasAction()
    {
        $result = ['status' => 'failed'];

        if (!$this->request->isPost()) {
            return $result;
        }

        $name = $this->request->getPost('name', 'string', '');
        if (empty($name) || !preg_match('/^[a-zA-Z0-9_]{1,31}$/', $name)) {
            $result['message'] = 'Invalid alias name';
            return $result;
        }

        // Check if alias already exists
        $configObj = Config::getInstance();
        $xml = $configObj->object();

        if (isset($xml->OPNsense->Firewall->Alias->aliases)) {
            foreach ($xml->OPNsense->Firewall->Alias->aliases->children() as $alias) {
                if ($alias->getName() === 'alias' && (string)$alias->name === $name) {
                    $result['message'] = 'Alias already exists';
                    return $result;
                }
            }
        }

        // Create the alias via OPNsense's Firewall Alias model
        $mdl = new \OPNsense\Firewall\Alias();
        $node = $mdl->aliases->alias->Add();
        $node->name = $name;
        $node->type = 'external';
        $node->description = 'Managed by Aliaser plugin';
        $node->proto = '';
        $node->content = '';

        $valMsgs = $mdl->performValidation();
        $errors = [];
        foreach ($valMsgs as $msg) {
            $errors[] = $msg->getMessage();
        }

        if (!empty($errors)) {
            $result['message'] = implode('; ', $errors);
            return $result;
        }

        $mdl->serializeToConfig();
        $configObj->save();

        // Apply the alias so pf creates the table
        $backend = new \OPNsense\Core\Backend();
        $backend->configdRun('filter reload');

        $result = ['status' => 'ok', 'name' => $name];
        return $result;
    }
}
