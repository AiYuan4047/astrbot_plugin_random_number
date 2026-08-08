// 随机数插件管理面板
let currentModule = '';
let autoRefreshTimer = null;
let bridge = null;

// 等待 bridge 准备就绪
async function waitForBridge() {
    return new Promise((resolve) => {
        if (window.AstrBotPluginPage) {
            resolve(window.AstrBotPluginPage);
            return;
        }
        
        const checkInterval = setInterval(() => {
            if (window.AstrBotPluginPage) {
                clearInterval(checkInterval);
                resolve(window.AstrBotPluginPage);
            }
        }, 100);
        
        // 5秒超时
        setTimeout(() => {
            clearInterval(checkInterval);
            resolve(window.AstrBotPluginPage);
        }, 5000);
    });
}

// 初始化
document.addEventListener('DOMContentLoaded', async () => {
    bridge = await waitForBridge();
    if (bridge) {
        loadData();
        startAutoRefresh();
    }
});

// 启动自动刷新（每5秒）
function startAutoRefresh() {
    if (autoRefreshTimer) {
        clearInterval(autoRefreshTimer);
    }
    autoRefreshTimer = setInterval(() => {
        loadData();
    }, 5000);
}

// 加载数据
async function loadData() {
    if (!bridge) {
        return;
    }
    
    try {
        // 加载统计数据
        const stats = await bridge.apiGet('stats');
        console.log('[随机数] 统计数据:', stats);
        updateStats(stats);
        
        // 加载记录列表
        const params = {};
        if (currentModule) {
            params.module = currentModule;
        }
        const records = await bridge.apiGet('records', params);
        console.log('[随机数] 记录列表:', records);
        renderRecords(records);
        
    } catch (error) {
        console.error('[随机数] 加载数据失败:', error);
    }
}

// 更新统计显示
function updateStats(stats) {
    document.getElementById('statRandomNumber').textContent = stats.random_number || 0;
    document.getElementById('statCoinFlip').textContent = stats.coin_flip || 0;
    document.getElementById('statMemberLottery').textContent = stats.member_lottery || 0;
    document.getElementById('statTotal').textContent = stats.total || 0;
}

// 切换模块筛选
function switchModule(element, moduleKey) {
    // 移除所有卡片的active状态
    const cards = document.querySelectorAll('.stat-card');
    cards.forEach(card => card.classList.remove('active'));
    
    // 给当前卡片添加active状态
    element.classList.add('active');
    
    // 更新当前模块
    currentModule = moduleKey;
    
    // 更新标题
    const moduleNames = {
        '': '全部记录',
        'random_number': '随机数',
        'coin_flip': '抛硬币',
        'member_lottery': '成员抽奖'
    };
    document.getElementById('listTitle').textContent = moduleNames[moduleKey] || '全部记录';
    
    // 加载数据
    loadData();
}

// 渲染记录列表
function renderRecords(records) {
    const tbody = document.getElementById('recordTableBody');
    
    if (!records || records.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty">暂无记录</td></tr>';
        return;
    }
    
    tbody.innerHTML = records.map(record => {
        const moduleClass = 'module-' + record.module;
        
        return `
            <tr onclick="showRecordDetail(${record.id})" style="cursor: pointer;">
                <td>#${record.id}</td>
                <td>${escapeHtml(record.user_id)}</td>
                <td><span class="module-badge ${moduleClass}">${record.module_name}</span></td>
                <td class="request-cell" title="${escapeHtml(record.request)}">${escapeHtml(record.request)}</td>
                <td class="request-cell" title="${escapeHtml(record.result)}">${escapeHtml(record.result)}</td>
                <td>${escapeHtml(record.source_group)}</td>
                <td>${record.created_at}</td>
            </tr>
        `;
    }).join('');
}

// 显示记录详情
async function showRecordDetail(recordId) {
    if (!bridge) {
        return;
    }
    
    try {
        const record = await bridge.apiGet('records/detail', { id: recordId });
        console.log('[随机数] 记录详情:', record);
        
        const moduleClass = 'module-' + record.module;
        
        document.getElementById('recordDetailContent').innerHTML = `
            <div class="record-detail-section">
                <div class="record-detail-label">板块</div>
                <div class="record-detail-value">
                    <span class="module-badge ${moduleClass}">${record.module_name}</span>
                </div>
            </div>
            
            <div class="record-detail-section">
                <div class="record-detail-label">用户请求</div>
                <div class="record-detail-value original-message">${escapeHtml(record.request)}</div>
            </div>
            
            <div class="record-detail-section">
                <div class="record-detail-label">生成结果</div>
                <div class="record-detail-value original-message">${escapeHtml(record.result)}</div>
            </div>
            
            <div class="record-detail-meta">
                <div class="record-detail-meta-item">记录编号: #${record.id}</div>
                <div class="record-detail-meta-item">用户: ${escapeHtml(record.user_id)}</div>
                <div class="record-detail-meta-item">来源: ${escapeHtml(record.source_group)}</div>
                <div class="record-detail-meta-item">时间: ${record.created_at}</div>
            </div>
        `;
        
        document.getElementById('listView').classList.remove('active');
        document.getElementById('recordDetailView').classList.add('active');
    } catch (error) {
        console.error('[随机数] 加载记录详情失败:', error);
        showToast('加载记录详情失败');
    }
}

// 返回列表
function backToList() {
    document.getElementById('recordDetailView').classList.remove('active');
    document.getElementById('listView').classList.add('active');
    loadData();
}

// 显示清空确认弹窗
function showClearConfirm() {
    document.getElementById('confirmTitle').textContent = '确认清空';
    document.getElementById('confirmMessage').textContent = '确定要清空所有使用记录吗？此操作不可恢复！';
    document.getElementById('confirmOkBtn').onclick = clearAllRecords;
    document.getElementById('confirmModal').classList.add('active');
}

// 关闭确认弹窗
function closeConfirm() {
    document.getElementById('confirmModal').classList.remove('active');
}

// 清空所有记录
async function clearAllRecords() {
    if (!bridge) {
        return;
    }
    
    try {
        const result = await bridge.apiPost('records/clear', {});
        showToast(result.message || '已清空');
        closeConfirm();
        loadData();
    } catch (error) {
        console.error('[随机数] 清空记录失败:', error);
        showToast('清空记录失败');
    }
}

// HTML 转义
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 显示提示
function showToast(message) {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 3000);
}

// 暴露到全局
window.switchModule = switchModule;
window.showRecordDetail = showRecordDetail;
window.backToList = backToList;
window.showClearConfirm = showClearConfirm;
window.closeConfirm = closeConfirm;
window.loadData = loadData;
