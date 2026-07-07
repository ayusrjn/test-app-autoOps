// Chronos App Logic

document.addEventListener('DOMContentLoaded', () => {
    // State
    let products = [];
    let cart = { items: [], total_price: 0.0 };
    let currentBrandFilter = 'all';

    // DOM Elements
    const productsContainer = document.getElementById('products-container');
    const cartItemsContainer = document.getElementById('cart-items-container');
    const cartTotal = document.getElementById('cart-total');
    const cartCount = document.getElementById('cart-count');
    const cartToggleBtn = document.getElementById('cart-toggle-btn');
    const clearCartBtn = document.getElementById('clear-cart-btn');
    const checkoutBtn = document.getElementById('checkout-btn');
    const viewOrdersBtn = document.getElementById('view-orders-btn');
    const ordersModal = document.getElementById('orders-modal');
    const closeModalBtn = document.getElementById('close-modal-btn');
    const ordersTbody = document.getElementById('orders-tbody');
    const filterBtns = document.querySelectorAll('.filter-btn');

    // Simulator Elements
    const simStatusText = document.getElementById('sim-status-text');
    const simStatusIndicator = document.querySelector('.sim-status .status-indicator');
    
    // Initialize
    loadProducts();
    loadCart();

    // Event Listeners
    filterBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            filterBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentBrandFilter = btn.dataset.brand;
            renderProducts();
        });
    });

    // Cart actions
    clearCartBtn.addEventListener('click', clearCart);
    checkoutBtn.addEventListener('click', handleCheckout);

    // Modal
    viewOrdersBtn.addEventListener('click', openOrdersModal);
    closeModalBtn.addEventListener('click', closeOrdersModal);
    ordersModal.addEventListener('click', (e) => {
        if (e.target === ordersModal) closeOrdersModal();
    });

    // Telemetry Simulators
    setupSimulatorButton('sim-slow', '/api/simulate/slow-checkout', 'Slow Checkout Triggered (5s)...', 'Slow Checkout Completed');
    setupSimulatorButton('sim-error', '/api/simulate/payment-error', 'Triggering Payment Timeout Simulation...', 'Payment Simulation Response Received');
    setupSimulatorButton('sim-cpu', '/api/simulate/cpu-load', 'Running heavy CPU encryption calculations...', 'CPU Spike Completed');
    setupSimulatorButton('sim-db', '/api/simulate/db-lock', 'Simulating Database Transaction Lock (3s)...', 'DB Lock Completed');
    setupSimulatorButton('sim-memory', '/api/simulate/memory-leak', 'Leaking 1,000,000 items to list...', 'Memory Leak Completed');
    setupSimulatorButton('sim-external', '/api/simulate/external', 'Calling external payment gateway (httpbin.org)...', 'External API Call Completed');

    // Functions
    async function loadProducts() {
        try {
            const res = await fetch('/api/products');
            if (!res.ok) throw new Error("Failed to fetch products");
            products = await res.json();
            renderProducts();
        } catch (err) {
            productsContainer.innerHTML = `<div class="loader text-danger"><i class="fa-solid fa-triangle-exclamation"></i> Error loading collection: ${err.message}</div>`;
        }
    }

    async function loadCart() {
        try {
            const res = await fetch('/api/cart');
            if (!res.ok) throw new Error("Failed to fetch cart");
            cart = await res.json();
            renderCart();
        } catch (err) {
            console.error("Cart error:", err);
        }
    }

    function renderProducts() {
        const filtered = currentBrandFilter === 'all' 
            ? products 
            : products.filter(p => p.brand === currentBrandFilter);

        if (filtered.length === 0) {
            productsContainer.innerHTML = `<div class="loader">No watches found in this category.</div>`;
            return;
        }

        productsContainer.innerHTML = filtered.map(product => {
            const isOutOfStock = product.stock <= 0;
            return `
                <div class="product-card">
                    <div class="product-img-wrapper">
                        <img src="${product.image_url}" alt="${product.name}">
                        <span class="product-brand">${product.brand}</span>
                    </div>
                    <div class="product-info">
                        <h4 class="product-title">${product.name}</h4>
                        <p class="product-desc">${product.description}</p>
                        <div class="product-footer">
                            <div>
                                <span class="product-price">$${product.price.toLocaleString()}</span>
                                <span class="stock-tag ${isOutOfStock ? 'stock-out' : ''}">
                                    ${isOutOfStock ? 'Out of Stock' : `${product.stock} available`}
                                </span>
                            </div>
                            <button class="btn primary-btn add-to-cart-btn" 
                                    data-id="${product.id}" 
                                    ${isOutOfStock ? 'disabled' : ''}>
                                <i class="fa-solid fa-cart-plus"></i> Add
                            </button>
                        </div>
                    </div>
                </div>
            `;
        }).join('');

        // Attach event listeners to newly created buttons
        document.querySelectorAll('.add-to-cart-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const id = parseInt(btn.dataset.id);
                addToCart(id);
            });
        });
    }

    function renderCart() {
        // Count total quantities
        const count = cart.items.reduce((acc, item) => acc + item.quantity, 0);
        cartCount.textContent = count;

        if (cart.items.length === 0) {
            cartItemsContainer.innerHTML = `<div class="empty-cart-message">Your cart is empty. Add some watches to begin.</div>`;
            cartTotal.textContent = "$0.00";
            checkoutBtn.disabled = true;
            return;
        }

        checkoutBtn.disabled = false;
        cartTotal.textContent = `$${cart.total_price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;

        cartItemsContainer.innerHTML = cart.items.map(item => `
            <div class="cart-item">
                <img src="${item.product.image_url}" alt="${item.product.name}" class="cart-item-img">
                <div class="cart-item-details">
                    <div class="cart-item-title">${item.product.name}</div>
                    <div class="cart-item-brand">${item.product.brand}</div>
                    <div class="cart-item-subtotal">$${item.product.price.toLocaleString()} &times; ${item.quantity}</div>
                </div>
                <div class="cart-item-qty-actions">
                    <button class="remove-item-btn" data-id="${item.product.id}" title="Remove item">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </div>
            </div>
        `).join('');

        // Attach remove action
        document.querySelectorAll('.remove-item-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const id = parseInt(btn.dataset.id);
                removeFromCart(id);
            });
        });
    }

    async function addToCart(productId) {
        try {
            const res = await fetch('/api/cart/add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ product_id: productId, quantity: 1 })
            });

            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Failed to add item to cart");
            
            await loadCart();
            // Refresh catalog stocks in UI
            await loadProducts();
        } catch (err) {
            alert(err.message);
        }
    }

    async function removeFromCart(productId) {
        try {
            const res = await fetch('/api/cart/remove', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ product_id: productId })
            });

            if (!res.ok) throw new Error("Failed to remove item");
            await loadCart();
            await loadProducts();
        } catch (err) {
            console.error(err);
        }
    }

    async function clearCart() {
        try {
            const res = await fetch('/api/cart/clear', { method: 'POST' });
            if (!res.ok) throw new Error("Failed to clear cart");
            await loadCart();
            await loadProducts();
        } catch (err) {
            console.error(err);
        }
    }

    async function handleCheckout() {
        checkoutBtn.disabled = true;
        checkoutBtn.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> Processing...`;
        
        // Show status in simulator panel too since checkout triggers OTLP tracing
        updateSimStatus('running', 'Checkout pipeline active - checking stock, database write, and external gateway...');

        try {
            const res = await fetch('/api/checkout', { method: 'POST' });
            const data = await res.json();
            
            if (!res.ok) throw new Error(data.detail || "Checkout failed");

            updateSimStatus('success', `Checkout success! Order ID: ${data.order_id}`);
            alert(`Purchase complete! Order ID: ${data.order_id}\nTotal: $${data.total_price.toLocaleString()}`);
            
            await loadCart();
            await loadProducts();
        } catch (err) {
            updateSimStatus('error', `Checkout Error: ${err.message}`);
            alert(`Checkout Error: ${err.message}`);
        } finally {
            checkoutBtn.innerHTML = `Checkout`;
            checkoutBtn.disabled = false;
        }
    }

    // Modal Orders
    async function openOrdersModal() {
        ordersModal.classList.add('active');
        ordersTbody.innerHTML = `<tr><td colspan="4" style="text-align: center;"><i class="fa-solid fa-circle-notch fa-spin"></i> Loading order logs...</td></tr>`;
        
        try {
            const res = await fetch('/api/orders');
            if (!res.ok) throw new Error("Failed to fetch orders");
            const orders = await res.json();

            if (orders.length === 0) {
                ordersTbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-secondary);">No orders recorded yet.</td></tr>`;
                return;
            }

            ordersTbody.innerHTML = orders.map(order => {
                const dateStr = new Date(order.created_at).toLocaleString();
                const totalStr = `$${order.total_price.toLocaleString(undefined, {minimumFractionDigits: 2})}`;
                return `
                    <tr>
                        <td><strong>#${order.id}</strong></td>
                        <td>${dateStr}</td>
                        <td style="color: var(--gold); font-weight: 500;">${totalStr}</td>
                        <td>
                            <span class="status-badge ${order.status.toLowerCase()}">
                                ${order.status}
                            </span>
                        </td>
                    </tr>
                `;
            }).join('');
        } catch (err) {
            ordersTbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--danger);">${err.message}</td></tr>`;
        }
    }

    function closeOrdersModal() {
        ordersModal.classList.remove('active');
    }

    // Telemetry Simulators Helpers
    function setupSimulatorButton(btnId, endpoint, startMsg, successMsg) {
        const btn = document.getElementById(btnId);
        if (!btn) return;
        
        btn.addEventListener('click', async () => {
            // Disable button during execution
            btn.disabled = true;
            updateSimStatus('running', startMsg);
            
            try {
                const res = await fetch(endpoint);
                const data = await res.json();
                
                if (!res.ok) {
                    throw new Error(data.detail || `Server returned ${res.status}`);
                }
                
                let details = '';
                if (data.memory_list_size) details = ` (Current size: ${data.memory_list_size.toLocaleString()})`;
                if (data.external_status) details = ` (httpbin.org status: ${data.external_status})`;
                if (data.result) details = ` (Result: ${data.result})`;

                updateSimStatus('success', `${successMsg}${details}`);
            } catch (err) {
                updateSimStatus('error', `Failed: ${err.message}`);
            } finally {
                btn.disabled = false;
            }
        });
    }

    function updateSimStatus(state, message) {
        // Reset classes
        simStatusIndicator.className = 'status-indicator';
        simStatusIndicator.classList.add(state);
        simStatusText.textContent = message;
        
        // Console log for debug
        console.log(`[Simulator Status: ${state}] ${message}`);
    }
});
