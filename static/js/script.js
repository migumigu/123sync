/* ============================================
   123sync — 原生 JS（无 jQuery 依赖）
   ============================================ */
(function () {
    'use strict';

    // ---- Toast ----
    var toastTimer = null;

    function showToast(message, type) {
        type = type || 'success';
        var toast = document.getElementById('toast');
        toast.textContent = message;
        toast.className = 'toast ' + type;

        // 触发 reflow 确保动画生效
        void toast.offsetWidth;
        toast.classList.add('show');

        clearTimeout(toastTimer);
        toastTimer = setTimeout(function () {
            toast.classList.remove('show');
            setTimeout(function () {
                toast.classList.add('hidden');
            }, 300);
        }, 3000);
    }

    // ---- 规则管理 ----
    function createRuleRow(localPath, panPath) {
        var row = document.createElement('div');
        row.className = 'rule-row';

        var localInput = document.createElement('input');
        localInput.type = 'text';
        localInput.className = 'input input-path input-mono';
        localInput.name = 'local_path';
        localInput.placeholder = '本地路径';
        if (localPath) localInput.value = localPath;

        var arrow = document.createElement('span');
        arrow.className = 'arrow';
        arrow.textContent = '→';

        var panInput = document.createElement('input');
        panInput.type = 'text';
        panInput.className = 'input input-path input-mono';
        panInput.name = 'pan_path';
        panInput.placeholder = '网盘路径';
        if (panPath) panInput.value = panPath;

        var delBtn = document.createElement('button');
        delBtn.type = 'button';
        delBtn.className = 'btn-icon btn-danger remove-rule';
        delBtn.title = '删除规则';
        delBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M3 4h10M6 4V2.5h4V4M5 4l.5 9h5L11 4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>';
        delBtn.addEventListener('click', function () {
            row.remove();
            markDirty();
        });

        row.appendChild(localInput);
        row.appendChild(arrow);
        row.appendChild(panInput);
        row.appendChild(delBtn);

        // 输入变化标记未保存
        localInput.addEventListener('change', markDirty);
        panInput.addEventListener('change', markDirty);

        return row;
    }

    document.getElementById('add-rule').addEventListener('click', function () {
        var container = document.getElementById('rules-container');
        container.appendChild(createRuleRow());
    });

    // 删除已有规则
    document.querySelectorAll('.remove-rule').forEach(function (btn) {
        btn.addEventListener('click', function () {
            btn.closest('.rule-row').remove();
            markDirty();
        });
    });

    // ---- 配置收集 ----
    function collectGeneralConfig() {
        return {
            seconds_upload_min_size: document.getElementById('seconds_upload_min_size').value,
            duplicate_handling: document.getElementById('duplicate_handling').value,
            cron_expression: document.getElementById('cron_expression').value,
            force_upload_large_file: document.getElementById('force_upload_large_file').checked ? 'true' : 'false'
        };
    }

    function collectAccountConfig() {
        return {
            passport: document.getElementById('passport').value,
            password: document.getElementById('password').value,
            client_id: document.getElementById('client_id').value,
            client_secret: document.getElementById('client_secret').value
        };
    }

    function collectSyncRulesConfig() {
        var rules = {};
        var rows = document.querySelectorAll('#rules-container .rule-row');
        rows.forEach(function (row, index) {
            var localPath = row.querySelector('input[name="local_path"]').value.trim();
            var panPath = row.querySelector('input[name="pan_path"]').value.trim();
            if (localPath && panPath) {
                rules['rule' + (index + 1)] = localPath + ', ' + panPath;
            }
        });
        return rules;
    }

    // ---- 保存配置 ----
    function saveConfigSection(section, btn) {
        var configData;
        switch (section) {
            case 'General':
                configData = collectGeneralConfig();
                break;
            case 'Account':
                configData = collectAccountConfig();
                break;
            case 'SyncRules':
                configData = collectSyncRulesConfig();
                break;
            default:
                showToast('无效的配置部分', 'error');
                return;
        }

        var originalHTML = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span> 保存中...';

        fetch('/api/config/' + section, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ config: configData })
        })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.success) {
                    showToast(data.message || '配置保存成功', 'success');
                    isDirty = false;
                } else {
                    showToast(data.message || '配置保存失败', 'error');
                }
            })
            .catch(function (err) {
                showToast('配置保存失败：' + err.message, 'error');
            })
            .finally(function () {
                btn.disabled = false;
                btn.innerHTML = originalHTML;
            });
    }

    document.querySelectorAll('.save-section-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            saveConfigSection(btn.dataset.section, btn);
        });
    });

    // ---- 未保存提示 ----
    var isDirty = false;

    function markDirty() {
        isDirty = true;
    }

    document.querySelectorAll('input, select, textarea').forEach(function (el) {
        el.addEventListener('change', markDirty);
    });

    window.addEventListener('beforeunload', function (e) {
        if (isDirty) {
            e.preventDefault();
            e.returnValue = '您有未保存的更改，确定要离开吗？';
            return e.returnValue;
        }
    });

    // ---- 同步状态 ----
    var syncBadge = document.getElementById('sync-badge');
    var syncBadgeText = document.getElementById('sync-badge-text');
    var forceSyncBtn = document.getElementById('force-sync');

    function updateSyncStatusUI(isRunning) {
        if (isRunning) {
            syncBadge.className = 'sync-badge running';
            syncBadgeText.textContent = '同步中';
            forceSyncBtn.disabled = true;
            forceSyncBtn.innerHTML = '<span class="spinner"></span> 同步中';
        } else {
            syncBadge.className = 'sync-badge ready';
            syncBadgeText.textContent = '就绪';
            forceSyncBtn.disabled = false;
            forceSyncBtn.innerHTML = '<span class="btn-label">强制同步</span>';
        }
    }

    function checkSyncStatus() {
        fetch('/api/sync/status')
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.success) {
                    updateSyncStatusUI(data.is_force_sync_running);
                }
            })
            .catch(function () { /* 静默失败，下次重试 */ })
            .finally(function () {
                setTimeout(checkSyncStatus, 3000);
            });
    }

    // ---- 强制同步 ----
    forceSyncBtn.addEventListener('click', function () {
        if (!confirm('确定要执行强制同步吗？将立即同步所有文件。')) return;

        updateSyncStatusUI(true);
        showToast('强制同步已启动，正在执行...', 'warning');

        fetch('/api/sync/force', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.success) {
                    showToast('强制同步已成功启动', 'success');
                } else {
                    showToast(data.message || '强制同步启动失败', 'error');
                    updateSyncStatusUI(false);
                }
            })
            .catch(function (err) {
                showToast('强制同步启动失败：' + err.message, 'error');
                updateSyncStatusUI(false);
            });
    });

    // ---- 键盘快捷键 ----
    document.addEventListener('keydown', function (e) {
        // Ctrl/Cmd + S 保存（保存当前展开的第一个 section）
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
            e.preventDefault();
            var openPanel = document.querySelector('details[open] .save-section-btn');
            if (openPanel) openPanel.click();
        }
    });

    // ---- 启动 ----
    checkSyncStatus();
})();
