/**
 * Workflow Orchestration Engine - Dashboard JavaScript
 * Handles API communication, UI updates, and user interactions
 */

// API Configuration
const API_BASE_URL = 'http://localhost:5001';

// DOM Elements Cache
const elements = {
    apiStatus: document.getElementById('api-status'),
    dbStatus: document.getElementById('db-status'),
    redisStatus: document.getElementById('redis-status'),
    workflowCount: document.getElementById('workflow-count'),
    executionCount: document.getElementById('execution-count'),
    workflowsList: document.getElementById('workflows-list'),
    executionsList: document.getElementById('executions-list'),
    outputArea: document.getElementById('output-area')
};

/**
 * Makes an API request with error handling
 * @param {string} endpoint - API endpoint
 * @param {object} options - Fetch options
 * @returns {Promise<object>} - Response data
 */
async function apiRequest(endpoint, options = {}) {
    try {
        const response = await fetch(`${API_BASE_URL}${endpoint}`, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        return await response.json();
    } catch (error) {
        console.error(`API Error (${endpoint}):`, error);
        throw error;
    }
}

/**
 * Updates the health status indicators
 * @param {object} health - Health check response
 */
function updateHealthStatus(health) {
    elements.apiStatus.textContent = health.status === 'healthy' ? '✓ Online' : '✗ Offline';
    elements.dbStatus.textContent = health.database === 'healthy' ? '✓ Connected' : '✗ Error';
    elements.redisStatus.textContent = health.redis === 'healthy' ? '✓ Connected' : '✗ Error';
}

/**
 * Renders a workflow card
 * @param {object} workflow - Workflow data
 * @returns {string} - HTML string
 */
function renderWorkflowCard(workflow) {
    const stepsHtml = workflow.steps.length > 0 
        ? `<div class="steps-list">
            ${workflow.steps.map((step, index) => `
                <div class="step-item">
                    <span class="step-number">${index + 1}</span>
                    <span><strong>${step.name}</strong> → ${step.task_type}</span>
                </div>
            `).join('')}
           </div>`
        : '<div class="meta" style="margin-top:10px;">No steps defined</div>';
    
    return `
        <div class="workflow-card">
            <h4>${escapeHtml(workflow.name)} <span class="status-badge ${workflow.status}">${workflow.status}</span></h4>
            <div class="meta">ID: ${workflow.id}</div>
            <div class="meta">${escapeHtml(workflow.description) || 'No description'}</div>
            ${stepsHtml}
        </div>
    `;
}

/**
 * Renders an execution card
 * @param {object} execution - Execution data
 * @returns {string} - HTML string
 */
function renderExecutionCard(execution) {
    const startedAt = execution.started_at 
        ? new Date(execution.started_at).toLocaleString() 
        : 'Pending';
    
    const completedHtml = execution.status === 'completed' 
        ? `<div class="meta" style="color:#00ff88;">✓ Completed at ${new Date(execution.completed_at).toLocaleString()}</div>`
        : '';
    
    const errorHtml = execution.error_message 
        ? `<div class="meta error">Error: ${escapeHtml(execution.error_message)}</div>`
        : '';
    
    return `
        <div class="execution-card">
            <h4>Execution <span class="status-badge ${execution.status}">${execution.status}</span></h4>
            <div class="meta">ID: ${execution.id}</div>
            <div class="meta">Started: ${startedAt}</div>
            ${completedHtml}
            ${errorHtml}
        </div>
    `;
}

/**
 * Escapes HTML to prevent XSS
 * @param {string} text - Text to escape
 * @returns {string} - Escaped text
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Loads all dashboard data from the API
 */
async function loadData() {
    try {
        // Health check
        const health = await apiRequest('/health');
        updateHealthStatus(health);

        // Load workflows
        const workflows = await apiRequest('/api/v1/workflows');
        elements.workflowCount.textContent = workflows.count;
        
        if (workflows.workflows.length === 0) {
            elements.workflowsList.innerHTML = '<div class="empty-state">No workflows yet. Click "Create Demo Workflow" to get started!</div>';
        } else {
            elements.workflowsList.innerHTML = workflows.workflows.map(renderWorkflowCard).join('');
        }

        // Load executions
        const executions = await apiRequest('/api/v1/executions');
        elements.executionCount.textContent = executions.count;
        
        if (executions.executions.length === 0) {
            elements.executionsList.innerHTML = '<div class="empty-state">No executions yet. Run a workflow to see results!</div>';
        } else {
            elements.executionsList.innerHTML = executions.executions
                .slice(0, 5)
                .map(renderExecutionCard)
                .join('');
        }
    } catch (error) {
        elements.apiStatus.textContent = '✗ Offline';
        elements.apiStatus.style.color = '#ff4444';
        console.error('Failed to load data:', error);
    }
}

/**
 * Creates a demo workflow with a sample step
 */
async function createDemoWorkflow() {
    const output = elements.outputArea;
    output.innerHTML = '<div class="output-box">Creating workflow...</div>';
    
    try {
        // Create workflow
        const workflow = await apiRequest('/api/v1/workflows', {
            method: 'POST',
            body: JSON.stringify({ 
                name: 'demo-' + Date.now(), 
                description: 'Demo workflow created from dashboard' 
            })
        });
        
        // Add a step
        await apiRequest(`/api/v1/workflows/${workflow.id}/steps`, {
            method: 'POST',
            body: JSON.stringify({ 
                name: 'fetch_joke', 
                task_type: 'http_request', 
                step_order: 0,
                config: { 
                    url: 'https://official-joke-api.appspot.com/random_joke', 
                    method: 'GET' 
                }
            })
        });
        
        // Activate workflow
        await apiRequest(`/api/v1/workflows/${workflow.id}/activate`, {
            method: 'POST'
        });
        
        output.innerHTML = `<div class="output-box">✓ Created workflow: ${workflow.name}\n✓ Added step: fetch_joke\n✓ Activated!\n\nWorkflow ID: ${workflow.id}</div>`;
        
        // Refresh the dashboard
        await loadData();
    } catch (error) {
        output.innerHTML = `<div class="output-box error">Error: ${error.message}</div>`;
    }
}

/**
 * Runs the most recent active workflow
 */
async function runWorkflow() {
    const output = elements.outputArea;
    output.innerHTML = '<div class="output-box">Finding workflow to run...</div>';
    
    try {
        // Get active workflows
        const workflows = await apiRequest('/api/v1/workflows?status=active');
        
        if (workflows.workflows.length === 0) {
            output.innerHTML = '<div class="output-box">No active workflows. Create one first!</div>';
            return;
        }
        
        const workflow = workflows.workflows[0];
        output.innerHTML = `<div class="output-box">Running workflow: ${workflow.name}...</div>`;
        
        // Create execution
        const execution = await apiRequest('/api/v1/executions', {
            method: 'POST',
            body: JSON.stringify({ 
                workflow_id: workflow.id, 
                idempotency_key: 'run-' + Date.now() 
            })
        });
        
        // Poll for completion
        let result = execution;
        for (let i = 0; i < 10; i++) {
            await sleep(1000);
            result = await apiRequest(`/api/v1/executions/${execution.id}`);
            
            if (result.status === 'completed' || result.status === 'failed') {
                break;
            }
        }
        
        output.innerHTML = `<div class="output-box">Workflow: ${workflow.name}\nStatus: ${result.status.toUpperCase()}\n\nOutput:\n${JSON.stringify(result.output_data, null, 2)}</div>`;
        
        // Refresh the dashboard
        await loadData();
    } catch (error) {
        output.innerHTML = `<div class="output-box error">Error: ${error.message}</div>`;
    }
}

/**
 * Sleep utility function
 * @param {number} ms - Milliseconds to sleep
 * @returns {Promise} - Resolves after delay
 */
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Initialize the dashboard
 */
function init() {
    // Load initial data
    loadData();
    
    // Set up auto-refresh every 10 seconds
    setInterval(loadData, 10000);
    
    // Expose functions globally for button onclick handlers
    window.createDemoWorkflow = createDemoWorkflow;
    window.runWorkflow = runWorkflow;
    window.loadData = loadData;
}

// Start the application when DOM is ready
document.addEventListener('DOMContentLoaded', init);
