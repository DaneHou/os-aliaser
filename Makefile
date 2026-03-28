PLUGIN_NAME=	os-aliaser
PLUGIN_VERSION=	1.0.0

PREFIX?=	/usr/local
DESTDIR?=

SCRIPTS_DIR=	$(DESTDIR)$(PREFIX)/opnsense/scripts/OPNsense/Aliaser
MVC_DIR=	$(DESTDIR)$(PREFIX)/opnsense/mvc/app
ACTIONS_DIR=	$(DESTDIR)$(PREFIX)/opnsense/service/conf/actions.d
PLUGINS_DIR=	$(DESTDIR)$(PREFIX)/etc/inc/plugins.inc.d

.PHONY: all install install-plugin activate uninstall

all:
	@echo ""
	@echo "os-aliaser — Smart Firewall Alias Manager for OPNsense"
	@echo ""
	@echo "Targets:"
	@echo "  make install          Install plugin and activate"
	@echo "  make install-plugin   Install plugin files only"
	@echo "  make activate         Clear caches, restart services"
	@echo "  make uninstall        Remove all plugin files"
	@echo ""

install: install-plugin activate
	@echo ""
	@echo "=== Installation complete ==="
	@echo "Go to: Services > Aliaser"
	@echo ""

install-plugin:
	@echo ">>> Installing plugin files..."
	# Plugin hooks
	@mkdir -p $(PLUGINS_DIR)
	@cp src/etc/inc/plugins.inc.d/aliaser.inc $(PLUGINS_DIR)/

	# MVC controllers
	@mkdir -p $(MVC_DIR)/controllers/OPNsense/Aliaser/Api
	@mkdir -p $(MVC_DIR)/controllers/OPNsense/Aliaser/forms
	@cp src/opnsense/mvc/app/controllers/OPNsense/Aliaser/*.php \
		$(MVC_DIR)/controllers/OPNsense/Aliaser/
	@cp src/opnsense/mvc/app/controllers/OPNsense/Aliaser/Api/*.php \
		$(MVC_DIR)/controllers/OPNsense/Aliaser/Api/
	@cp src/opnsense/mvc/app/controllers/OPNsense/Aliaser/forms/*.xml \
		$(MVC_DIR)/controllers/OPNsense/Aliaser/forms/

	# MVC models
	@mkdir -p $(MVC_DIR)/models/OPNsense/Aliaser/ACL
	@mkdir -p $(MVC_DIR)/models/OPNsense/Aliaser/Menu
	@cp src/opnsense/mvc/app/models/OPNsense/Aliaser/Aliaser.php \
		$(MVC_DIR)/models/OPNsense/Aliaser/
	@cp src/opnsense/mvc/app/models/OPNsense/Aliaser/Aliaser.xml \
		$(MVC_DIR)/models/OPNsense/Aliaser/
	@cp src/opnsense/mvc/app/models/OPNsense/Aliaser/ACL/ACL.xml \
		$(MVC_DIR)/models/OPNsense/Aliaser/ACL/
	@cp src/opnsense/mvc/app/models/OPNsense/Aliaser/Menu/Menu.xml \
		$(MVC_DIR)/models/OPNsense/Aliaser/Menu/

	# MVC views
	@mkdir -p $(MVC_DIR)/views/OPNsense/Aliaser
	@if ls src/opnsense/mvc/app/views/OPNsense/Aliaser/*.volt 1>/dev/null 2>&1; then \
		cp src/opnsense/mvc/app/views/OPNsense/Aliaser/*.volt \
			$(MVC_DIR)/views/OPNsense/Aliaser/; \
	fi

	# Backend scripts
	@mkdir -p $(SCRIPTS_DIR)
	@cp src/opnsense/scripts/OPNsense/Aliaser/*.py $(SCRIPTS_DIR)/
	@chmod +x $(SCRIPTS_DIR)/*.py

	# Log rotation
	@mkdir -p $(DESTDIR)/etc/newsyslog.conf.d
	@cp src/etc/newsyslog.conf.d/aliaser.conf $(DESTDIR)/etc/newsyslog.conf.d/

	# configd actions
	@mkdir -p $(ACTIONS_DIR)
	@cp src/opnsense/service/conf/actions.d/actions_aliaser.conf $(ACTIONS_DIR)/

	# Runtime directories
	@mkdir -p /var/run/aliaser
	@mkdir -p /var/log/aliaser
	@echo ">>> Plugin files installed."

activate:
	@echo ">>> Activating plugin..."
	# Flush menu cache
	@rm -f /var/lib/php/tmp/opnsense_menu_cache.xml 2>/dev/null || true
	@rm -f /tmp/opnsense_menu_cache.xml 2>/dev/null || true
	# Verify plugin hooks load without PHP errors
	@echo ">>> Checking plugin for PHP errors..."
	@php -l $(PLUGINS_DIR)/aliaser.inc 2>&1 || true
	@php -l $(MVC_DIR)/models/OPNsense/Aliaser/Aliaser.php 2>&1 || true
	# Restart configd to pick up new actions
	@service configd restart 2>/dev/null || true
	# Restart web GUI
	@configctl webgui restart 2>/dev/null || service php_fpm restart 2>/dev/null || true
	@echo ""
	@echo ">>> Plugin activated."
	@echo ">>> Hard-refresh your browser (Ctrl+Shift+R) to see the menu."

uninstall:
	@echo ">>> Stopping daemon..."
	@$(PREFIX)/opnsense/scripts/OPNsense/Aliaser/aliaserd.py stop 2>/dev/null || true
	@echo ">>> Removing plugin files..."
	@rm -rf $(MVC_DIR)/controllers/OPNsense/Aliaser
	@rm -rf $(MVC_DIR)/models/OPNsense/Aliaser
	@rm -rf $(MVC_DIR)/views/OPNsense/Aliaser
	@rm -rf $(SCRIPTS_DIR)
	@rm -f $(ACTIONS_DIR)/actions_aliaser.conf
	@rm -f $(PLUGINS_DIR)/aliaser.inc
	@rm -f $(DESTDIR)/etc/newsyslog.conf.d/aliaser.conf
	@rm -f /var/run/aliaser.pid
	@rm -rf /var/run/aliaser
	@rm -f /var/lib/php/tmp/opnsense_menu_cache.xml 2>/dev/null || true
	@rm -f /tmp/opnsense_menu_cache.xml 2>/dev/null || true
	@service configd restart 2>/dev/null || true
	@echo ">>> Plugin removed."
