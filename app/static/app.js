// Elements
const catalogGrid = document.getElementById('catalog-grid');
const recGrid = document.getElementById('recommendations-grid');
const recSection = document.getElementById('recommendations-section');
const catalogEmpty = document.getElementById('catalog-empty');
const recEmpty = document.getElementById('recommendations-empty');
const errorState = document.getElementById('error-state');
const retryBtn = document.getElementById('retry-btn');
const resetBtn = document.getElementById('reset-demo-btn');
const statusMessage = document.getElementById('status-message');
const recLoading = document.getElementById('rec-loading');
const toastContainer = document.getElementById('toast-container');

// State
let abortController = null;
let debounceTimer = null;

const createSkeleton = () => {
    const el = document.createElement('div');
    el.className = 'item-card skeleton skeleton-card';
    return el;
};

const formatPrice = (price) => {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(price);
};

const createItemCard = (item, isRecommendation = false) => {
    const card = document.createElement('article');
    card.className = 'item-card';
    card.setAttribute('data-id', item.item_id);

    const tagsHtml = (item.tags || []).map(tag => `<span class="tag">${tag}</span>`).join('');
    const imageHtml = item.image_url 
        ? `<div class="item-poster"><img src="${item.image_url}" alt="Poster for ${item.title}" loading="lazy"></div>`
        : `<div class="item-poster placeholder-poster"><span>No Poster</span></div>`;
    
    card.innerHTML = `
        ${imageHtml}
        <div class="item-content">
            <div class="item-category">${item.category || 'Genre Unspecified'}</div>
            <h3>${item.title}</h3>
            <div class="item-tags">${tagsHtml}</div>
        </div>
        <div class="interaction-actions">
            <button class="btn btn-secondary action-view" aria-label="View Details for ${item.title}">Details</button>
            <button class="btn btn-primary action-buy" aria-label="Simulate Watch of ${item.title}">Watch (Demo)</button>
        </div>
    `;

    // Attach event listeners
    const viewBtn = card.querySelector('.action-view');
    const buyBtn = card.querySelector('.action-buy');

    viewBtn.addEventListener('click', () => handleInteraction(item.item_id, 'view'));
    buyBtn.addEventListener('click', () => handleInteraction(item.item_id, 'purchase'));

    return card;
};

const announce = (message) => {
    statusMessage.textContent = message;
};

const showToast = (message, type = 'success') => {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    // Add icon depending on type
    const icon = type === 'success' ? '✓' : 'ℹ';
    
    toast.innerHTML = `
        <span class="toast-icon">${icon}</span>
        <span class="toast-message">${message}</span>
    `;
    
    toastContainer.appendChild(toast);
    
    // Trigger animation
    requestAnimationFrame(() => {
        toast.classList.add('show');
    });
    
    // Remove after 3 seconds
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
};

const showError = (show) => {
    if (show) {
        errorState.classList.remove('hidden');
        catalogGrid.classList.add('hidden');
        recSection.classList.add('hidden');
        announce('Service is currently unavailable.');
    } else {
        errorState.classList.add('hidden');
        catalogGrid.classList.remove('hidden');
        recSection.classList.remove('hidden');
    }
};

const fetchCatalog = async () => {
    try {
        catalogGrid.innerHTML = '';
        for(let i=0; i<8; i++) catalogGrid.appendChild(createSkeleton());
        
        const res = await fetch('/v1/demo/catalog');
        if (!res.ok) throw new Error('Failed to fetch catalog');
        
        const data = await res.json();
        catalogGrid.innerHTML = '';
        
        if (!data.items || data.items.length === 0) {
            catalogEmpty.classList.remove('hidden');
        } else {
            catalogEmpty.classList.add('hidden');
            data.items.forEach(item => {
                catalogGrid.appendChild(createItemCard(item));
            });
            announce('Catalog loaded successfully.');
        }
        showError(false);
    } catch (error) {
        console.error(error);
        showError(true);
    }
};

const fetchRecommendations = async () => {
    if (abortController) {
        abortController.abort();
    }
    abortController = new AbortController();
    
    recLoading.classList.remove('hidden');
    recGrid.innerHTML = '';
    
    try {
        const res = await fetch('/v1/demo/recommendations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: "demo-user", limit: 4 }),
            signal: abortController.signal
        });
        
        if (!res.ok) throw new Error('Failed to fetch recommendations');
        
        const data = await res.json();
        recGrid.innerHTML = '';
        
        if (!data.recommendations || data.recommendations.length === 0) {
            recEmpty.classList.remove('hidden');
        } else {
            recEmpty.classList.add('hidden');
            data.recommendations.forEach(item => {
                // The recommendation response has item_id inside the model directly
                recGrid.appendChild(createItemCard(item, true));
            });
            announce('Recommendations updated.');
        }
    } catch (error) {
        if (error.name === 'AbortError') return;
        console.error(error);
        announce('Failed to update recommendations.');
    } finally {
        recLoading.classList.add('hidden');
    }
};

const handleInteraction = async (itemId, type) => {
    announce(`Simulating ${type} for item...`);
    const actionName = type === 'purchase' ? 'Watched' : 'Viewed';
    
    try {
        const res = await fetch('/v1/demo/interactions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: "demo-user", // Overridden by backend session
                item_id: itemId,
                interaction_type: type
            })
        });
        
        if (!res.ok) throw new Error('Interaction failed');
        
        showToast(`${actionName} movie successfully! Recommendations updating...`, 'success');
        
        // Debounce recommendation fetch
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            fetchRecommendations();
        }, 500);
        
    } catch (error) {
        console.error(error);
        announce(`Failed to record ${type}.`);
        showToast(`Failed to record ${type}.`, 'error');
    }
};

const resetSession = async () => {
    announce('Resetting demo session...');
    try {
        const res = await fetch('/v1/demo/reset', { method: 'POST' });
        if (!res.ok) throw new Error('Reset failed');
        recGrid.innerHTML = '';
        recEmpty.classList.remove('hidden');
        announce('Demo session reset.');
    } catch (error) {
        console.error(error);
        announce('Failed to reset session.');
    }
};

// Event Listeners
retryBtn.addEventListener('click', fetchCatalog);
resetBtn.addEventListener('click', resetSession);

// Init
document.addEventListener('DOMContentLoaded', () => {
    fetchCatalog();
    fetchRecommendations();
});
