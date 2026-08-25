/* ── State ──────────────────────────────────────────────────────────────── */
let token = localStorage.getItem('ss_token') || null;
let currentUser = null;
let allProducts = [];
let saleItems = [];
let allDocuments = [];
let revenueChart = null;
let forecastChart = null;
let forecastProductId = null;

const API = '';   // same origin

/* ── Helpers ────────────────────────────────────────────────────────────── */
async function apiFetch(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(API + path, { ...opts, headers: { ...headers, ...(opts.headers || {}) } });
  if (res.status === 401) { logout(); return null; }
  const data = await res.json().catch(() => null);
  if (res.status === 402) {
    document.getElementById('license-banner').style.display = 'block';
    throw new Error(data?.detail || 'Your license has expired. Please renew.');
  }
  if (!res.ok) throw new Error(data?.detail || 'Request failed');
  return data;
}

function toast(msg, type = 'info') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.display = 'block';
  t.style.borderColor = type === 'error' ? 'var(--red)' : type === 'ok' ? 'var(--green)' : 'var(--border)';
  setTimeout(() => t.style.display = 'none', 3000);
}

function fmt(n) { return 'KES ' + Number(n).toLocaleString('en-KE', { minimumFractionDigits: 2 }); }

function openModal(id) { document.getElementById(id).style.display = 'flex'; }
function closeModal(id) { document.getElementById(id).style.display = 'none'; }

/* ── Auth ────────────────────────────────────────────────────────────────── */
function switchTab(tab) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelector(`.tab[onclick="switchTab('${tab}')"]`).classList.add('active');
  document.getElementById('login-form').style.display   = tab === 'login'    ? '' : 'none';
  document.getElementById('register-form').style.display = tab === 'register' ? '' : 'none';
  document.getElementById('forgot-form').style.display = 'none';
  document.getElementById('reset-form').style.display = 'none';
  hideAuthMessages();
}

function hideAuthMessages() {
  document.getElementById('auth-error').style.display = 'none';
  document.getElementById('auth-success').style.display = 'none';
}

function showAuthError(msg) {
  hideAuthMessages();
  const el = document.getElementById('auth-error');
  el.textContent = msg; el.style.display = 'block';
}

function showAuthSuccess(msg) {
  hideAuthMessages();
  const el = document.getElementById('auth-success');
  el.textContent = msg; el.style.display = 'block';
}

function showLoginForm() {
  document.querySelectorAll('.tab-row .tab')[0]?.classList.add('active');
  document.querySelectorAll('.tab-row .tab')[1]?.classList.remove('active');
  document.getElementById('login-form').style.display = '';
  document.getElementById('register-form').style.display = 'none';
  document.getElementById('forgot-form').style.display = 'none';
  document.getElementById('reset-form').style.display = 'none';
  hideAuthMessages();
}

function showForgotForm() {
  document.getElementById('login-form').style.display = 'none';
  document.getElementById('register-form').style.display = 'none';
  document.getElementById('forgot-form').style.display = '';
  document.getElementById('reset-form').style.display = 'none';
  hideAuthMessages();
}

function showResetForm() {
  document.getElementById('login-form').style.display = 'none';
  document.getElementById('register-form').style.display = 'none';
  document.getElementById('forgot-form').style.display = 'none';
  document.getElementById('reset-form').style.display = '';
  hideAuthMessages();
}

async function requestPasswordReset() {
  const email = document.getElementById('forgot-email').value.trim();
  if (!email) { showAuthError('Enter your email first.'); return; }
  try {
    const res = await fetch('/api/auth/forgot-password', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Something went wrong');
    showAuthSuccess(data.message || 'If that email is registered, a reset link has been sent.');
  } catch (e) {
    showAuthError(e.message);
  }
}

async function submitPasswordReset() {
  const pass = document.getElementById('reset-password').value;
  const confirm = document.getElementById('reset-password-confirm').value;
  const resetToken = new URLSearchParams(window.location.search).get('reset_token');

  if (!resetToken) { showAuthError('Reset link is missing or invalid.'); return; }
  if (!pass || pass.length < 6) { showAuthError('Password must be at least 6 characters.'); return; }
  if (pass !== confirm) { showAuthError('Passwords do not match.'); return; }

  try {
    const res = await fetch('/api/auth/reset-password', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: resetToken, new_password: pass })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Reset failed');
    showAuthSuccess('Password updated  you can sign in now.');
    // Clean the token out of the URL and return to the sign-in tab
    window.history.replaceState({}, document.title, window.location.pathname);
    setTimeout(showLoginForm, 1200);
  } catch (e) {
    showAuthError(e.message);
  }
}

async function login() {
  const email = document.getElementById('login-email').value;
  const pass  = document.getElementById('login-password').value;
  try {
    const form = new URLSearchParams({ username: email, password: pass });
    const res = await fetch('/api/auth/login', {
      method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: form.toString()
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Login failed');
    token = data.access_token;
    localStorage.setItem('ss_token', token);
    await initApp();
  } catch (e) {
    const el = document.getElementById('auth-error');
    el.textContent = e.message; el.style.display = 'block';
  }
}

async function register() {
  try {
    await apiFetch('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({
        name: document.getElementById('reg-name').value,
        email: document.getElementById('reg-email').value,
        password: document.getElementById('reg-password').value,
        business_name: document.getElementById('reg-business').value,
      })
    });
    toast('Account created! Please sign in.', 'ok');
    switchTab('login');
  } catch (e) {
    const el = document.getElementById('auth-error');
    el.textContent = e.message; el.style.display = 'block';
  }
}

function logout() {
  token = null; localStorage.removeItem('ss_token');
  document.getElementById('app').style.display = 'none';
  document.getElementById('auth-screen').style.display = 'flex';
}

/* ── Init ────────────────────────────────────────────────────────────────── */
async function initApp() {
  try {
    currentUser = await apiFetch('/api/auth/me');
    if (!currentUser) return;
    document.getElementById('auth-screen').style.display = 'none';
    document.getElementById('app').style.display = 'flex';
    document.getElementById('sidebar-user').textContent = currentUser.business_name || currentUser.name;
    await loadLicenseStatus();
    await Promise.all([loadProducts(), loadAnalytics(), loadAlerts()]);
    showPage('dashboard');
  } catch (e) { logout(); }
}

/* ── Navigation ──────────────────────────────────────────────────────────── */
function showPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
  document.getElementById('page-' + name).classList.add('active');
  document.querySelector(`[data-page="${name}"]`)?.classList.add('active');

  if (name === 'sales' || name === 'stock' || name === 'forecast') populateProductSelects();
  if (name === 'alerts') loadAlerts();
  if (name === 'dashboard') loadAnalytics();
  if (name === 'documents') loadDocuments();
  if (name === 'subscription') loadLicenseStatus();
}

/* ── Products ────────────────────────────────────────────────────────────── */
async function loadProducts() {
  const lowStock = document.getElementById('low-stock-filter')?.checked;
  try {
    allProducts = await apiFetch(`/api/products${lowStock ? '?low_stock_only=true' : ''}`) || [];
  } catch (e) { allProducts = []; }
  renderProductsTable(allProducts);
}

function filterProducts() {
  const q = document.getElementById('product-search').value.toLowerCase();
  renderProductsTable(allProducts.filter(p => p.name.toLowerCase().includes(q) || (p.sku||'').toLowerCase().includes(q)));
}

function renderProductsTable(products) {
  const tbody = document.getElementById('products-tbody');
  if (!products.length) { tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--text-muted);padding:2rem">No products yet  add your first one.</td></tr>'; return; }
  tbody.innerHTML = products.map(p => {
    const pct = p.reorder_point > 0 ? (p.current_stock / p.reorder_point) : 1;
    const statusClass = p.current_stock === 0 ? 'pill-out' : pct <= 1 ? 'pill-low' : 'pill-ok';
    const statusLabel = p.current_stock === 0 ? 'Out' : pct <= 1 ? 'Low' : 'OK';
    return `<tr>
      <td><strong>${p.name}</strong></td>
      <td style="color:var(--text-muted)">${p.sku || ''}</td>
      <td>${p.current_stock} ${p.unit}</td>
      <td>${p.reorder_point} ${p.unit}</td>
      <td>${fmt(p.cost_price)}</td>
      <td>${fmt(p.selling_price)}</td>
      <td>${taxBadge(p)}</td>
      <td><span class="pill ${statusClass}">${statusLabel}</span></td>
      <td>
        <button class="btn-ghost btn-sm" onclick="openEditProduct(${p.id})">Edit</button>
      </td>
    </tr>`;
  }).join('');
}

/* ── Tax (Kenya VAT) ─────────────────────────────────────────────────────── */
const DEFAULT_TAX_RATES = { STANDARD: 16, ZERO_RATED: 0, EXEMPT: 0 };

function onTaxCategoryChange() {
  const cat = document.getElementById('p-tax-category').value;
  const rateInput = document.getElementById('p-tax-rate');
  if (cat === 'REDUCED') {
    rateInput.disabled = false;
    if (!rateInput.value || rateInput.value === '16' || rateInput.value === '0') rateInput.value = 8;
  } else {
    rateInput.value = DEFAULT_TAX_RATES[cat] ?? 16;
    rateInput.disabled = true;
  }
}

function taxBadge(product) {
  const cat = product.tax_category || 'STANDARD';
  const rate = product.tax_rate ?? 16;
  const label = cat === 'STANDARD' ? `VAT ${rate}%`
    : cat === 'REDUCED' ? `VAT ${rate}%`
    : cat === 'ZERO_RATED' ? 'Zero-rated'
    : 'Exempt';
  return `<span class="pill pill-ok">${label}</span>`;
}

function openEditProduct(id) {
  const p = allProducts.find(x => x.id === id);
  if (!p) return;
  document.getElementById('product-modal-title').textContent = 'Edit Product';
  document.getElementById('edit-product-id').value = p.id;
  document.getElementById('p-name').value = p.name;
  document.getElementById('p-sku').value = p.sku || '';
  document.getElementById('p-cost').value = p.cost_price;
  document.getElementById('p-price').value = p.selling_price;
  document.getElementById('p-stock').value = p.current_stock;
  document.getElementById('p-unit').value = p.unit;
  document.getElementById('p-reorder-point').value = p.reorder_point;
  document.getElementById('p-reorder-qty').value = p.reorder_quantity;
  document.getElementById('p-desc').value = p.description || '';
  document.getElementById('p-tax-category').value = p.tax_category || 'STANDARD';
  document.getElementById('p-tax-rate').value = p.tax_rate ?? 16;
  onTaxCategoryChange();
  if (p.tax_category === 'REDUCED') document.getElementById('p-tax-rate').value = p.tax_rate ?? 8;
  openModal('product-modal');
}

function openAddProduct() {
  document.getElementById('product-modal-title').textContent = 'Add Product';
  document.getElementById('edit-product-id').value = '';
  ['p-name','p-sku','p-desc'].forEach(id => document.getElementById(id).value = '');
  ['p-cost','p-price'].forEach(id => document.getElementById(id).value = '');
  ['p-stock','p-reorder-point','p-reorder-qty'].forEach(id => document.getElementById(id).value = '0');
  document.getElementById('p-tax-category').value = 'STANDARD';
  onTaxCategoryChange();
  openModal('product-modal');
}
document.addEventListener('DOMContentLoaded', () => {
  document.querySelector('[onclick="openModal(\'product-modal\')"]')?.addEventListener('click', (e) => {
    e.preventDefault(); openAddProduct();
  });
});

async function saveProduct() {
  const editId = document.getElementById('edit-product-id').value;
  const payload = {
    name: document.getElementById('p-name').value,
    sku: document.getElementById('p-sku').value || null,
    description: document.getElementById('p-desc').value || null,
    unit: document.getElementById('p-unit').value,
    cost_price: parseFloat(document.getElementById('p-cost').value),
    selling_price: parseFloat(document.getElementById('p-price').value),
    current_stock: parseFloat(document.getElementById('p-stock').value) || 0,
    reorder_point: parseFloat(document.getElementById('p-reorder-point').value) || 0,
    reorder_quantity: parseFloat(document.getElementById('p-reorder-qty').value) || 0,
    tax_category: document.getElementById('p-tax-category').value,
    tax_rate: parseFloat(document.getElementById('p-tax-rate').value) || 0,
  };
  try {
    if (editId) {
      await apiFetch(`/api/products/${editId}`, { method: 'PATCH', body: JSON.stringify(payload) });
      toast('Product updated', 'ok');
    } else {
      await apiFetch('/api/products', { method: 'POST', body: JSON.stringify(payload) });
      toast('Product added', 'ok');
    }
    closeModal('product-modal');
    await loadProducts();
  } catch (e) { toast(e.message, 'error'); }
}

/* ── Product Selects ─────────────────────────────────────────────────────── */
function populateProductSelects() {
  const selects = ['sale-product-select', 'stock-product-select', 'forecast-product-select'];
  selects.forEach(id => {
    const sel = document.getElementById(id);
    if (!sel) return;
    const current = sel.value;
    sel.innerHTML = '<option value="">Select product…</option>' +
      allProducts.map(p => `<option value="${p.id}" data-price="${p.selling_price}">${p.name} (${p.current_stock} ${p.unit})</option>`).join('');
    if (current) sel.value = current;
  });

  // Auto-fill price when product selected in sale
  document.getElementById('sale-product-select')?.addEventListener('change', function() {
    const opt = this.selectedOptions[0];
    if (opt?.dataset.price) document.getElementById('sale-price').value = opt.dataset.price;
  });
}

/* ── Sales ───────────────────────────────────────────────────────────────── */
function itemVatRate(product) {
  if (!product) return 0;
  return (product.tax_category === 'STANDARD' || product.tax_category === 'REDUCED') ? (product.tax_rate ?? 0) : 0;
}

function addSaleItem() {
  const sel = document.getElementById('sale-product-select');
  const productId = parseInt(sel.value);
  const qty = parseFloat(document.getElementById('sale-qty').value);
  const price = parseFloat(document.getElementById('sale-price').value);
  if (!productId || !qty || !price) { toast('Fill in product, qty and price', 'error'); return; }
  const product = allProducts.find(p => p.id === productId);
  const vatRate = itemVatRate(product);
  const existing = saleItems.findIndex(i => i.product_id === productId);
  if (existing >= 0) {
    saleItems[existing].quantity += qty;
    saleItems[existing].subtotal = saleItems[existing].quantity * price;
    saleItems[existing].vat = saleItems[existing].subtotal * vatRate / 100;
  } else {
    const subtotal = qty * price;
    saleItems.push({
      product_id: productId, product_name: product.name, quantity: qty, unit_price: price,
      subtotal, vat_rate: vatRate, vat: subtotal * vatRate / 100,
    });
  }
  renderSaleItems();
}

function removeSaleItem(idx) { saleItems.splice(idx, 1); renderSaleItems(); }

function renderSaleItems() {
  const tbody = document.getElementById('sale-items-tbody');
  tbody.innerHTML = saleItems.map((item, i) => `
    <tr>
      <td>${item.product_name}</td>
      <td>${item.quantity}</td>
      <td>${fmt(item.unit_price)}</td>
      <td>${item.vat_rate ? fmt(item.vat) + ` (${item.vat_rate}%)` : ''}</td>
      <td>${fmt(item.subtotal)}</td>
      <td><button class="btn-ghost btn-sm" onclick="removeSaleItem(${i})">✕</button></td>
    </tr>`).join('');
  const subtotal = saleItems.reduce((s, i) => s + i.subtotal, 0);
  const vat = saleItems.reduce((s, i) => s + i.vat, 0);
  document.getElementById('sale-subtotal').textContent = fmt(subtotal);
  document.getElementById('sale-vat').textContent = fmt(vat);
  document.getElementById('sale-total').textContent = fmt(subtotal + vat);
}

function renderReceipt(sale) {
  const box = document.getElementById('sale-receipt');
  if (!sale) { box.style.display = 'none'; return; }
  const rows = sale.items.map(it => {
    const product = allProducts.find(p => p.id === it.product_id);
    const name = product ? product.name : `Product #${it.product_id}`;
    return `<tr>
      <td>${name}</td><td>${it.quantity}</td><td>${fmt(it.unit_price)}</td>
      <td>${it.tax_amount ? fmt(it.tax_amount) + ` (${it.tax_rate}%)` : ''}</td>
      <td>${fmt(it.subtotal + it.tax_amount)}</td>
    </tr>`;
  }).join('');
  box.innerHTML = `
    <h3 style="margin-bottom:.75rem">Receipt  Sale #${sale.id}</h3>
    <table class="data-table">
      <thead><tr><th>Product</th><th>Qty</th><th>Price</th><th>VAT</th><th>Total</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <div style="text-align:right;margin-top:.75rem;font-size:.9rem;color:var(--text-muted)">
      Subtotal: ${fmt(sale.subtotal_amount)} &nbsp;·&nbsp; VAT: ${fmt(sale.tax_amount)}
    </div>
    <div style="text-align:right;font-size:1.1rem;font-weight:600;margin-top:.25rem">
      Total: ${fmt(sale.total_amount)}
    </div>`;
  box.style.display = 'block';
}

async function submitSale() {
  if (!saleItems.length) { toast('Add at least one item', 'error'); return; }
  try {
    const sale = await apiFetch('/api/sales', {
      method: 'POST',
      body: JSON.stringify({
        items: saleItems.map(({ product_id, quantity, unit_price }) => ({ product_id, quantity, unit_price })),
        payment_method: document.getElementById('payment-method').value,
      })
    });
    saleItems = [];
    renderSaleItems();
    renderReceipt(sale);
    const msg = document.getElementById('sale-success');
    msg.textContent = '✓ Sale recorded successfully'; msg.style.display = 'block';
    setTimeout(() => msg.style.display = 'none', 3000);
    toast('Sale recorded', 'ok');
    await Promise.all([loadProducts(), loadAlerts()]);
  } catch (e) { toast(e.message, 'error'); }
}

/* ── Stock Movements ─────────────────────────────────────────────────────── */
async function recordStockMovement() {
  const productId = document.getElementById('stock-product-select').value;
  const qty = parseFloat(document.getElementById('stock-qty').value);
  const type = document.getElementById('stock-movement-type').value;
  const notes = document.getElementById('stock-notes').value;
  if (!productId || !qty) { toast('Select a product and enter quantity', 'error'); return; }
  try {
    await apiFetch('/api/stock/movement', {
      method: 'POST',
      body: JSON.stringify({ product_id: parseInt(productId), movement_type: type, quantity: qty, notes })
    });
    document.getElementById('stock-qty').value = '';
    document.getElementById('stock-notes').value = '';
    const msg = document.getElementById('stock-success');
    msg.textContent = '✓ Stock movement recorded'; msg.style.display = 'block';
    setTimeout(() => msg.style.display = 'none', 3000);
    toast('Stock updated', 'ok');
    await Promise.all([loadProducts(), loadAlerts()]);
    populateProductSelects();
  } catch (e) { toast(e.message, 'error'); }
}

/* ── Documents (Receipts / Invoices / Delivery Notes) ───────────────────────── */
function docTypeLabel(t) {
  return { RECEIPT: 'Receipt', INVOICE: 'Invoice', DELIVERY_NOTE: 'Delivery Note' }[t] || t;
}

async function loadDocuments() {
  const filter = document.getElementById('doc-type-filter')?.value || '';
  allDocuments = await apiFetch(`/api/documents${filter ? '?doc_type=' + filter : ''}`) || [];
  renderDocumentsTable(allDocuments);
}

function renderDocumentsTable(docs) {
  const tbody = document.getElementById('documents-tbody');
  if (!docs.length) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:2rem">No records yet  add one above.</td></tr>';
    return;
  }
  tbody.innerHTML = docs.map(d => {
    const fileCell = d.original_filename
      ? `<a href="#" onclick="viewDocument(${d.id}, ${JSON.stringify(d.original_filename)}); return false;">${d.original_filename}</a>`
      : '<span style="color:var(--text-muted)"></span>';
    return `<tr>
      <td><span class="pill pill-ok">${docTypeLabel(d.doc_type)}</span></td>
      <td>${d.reference_number || ''}</td>
      <td>${d.party_name || ''}</td>
      <td>${d.amount != null ? fmt(d.amount) : ''}</td>
      <td>${d.doc_date ? new Date(d.doc_date).toLocaleDateString() : ''}</td>
      <td>${fileCell}</td>
      <td><button class="btn-ghost btn-sm" onclick="deleteDocument(${d.id})">Delete</button></td>
    </tr>`;
  }).join('');
}

async function submitDocument() {
  const type = document.getElementById('doc-type').value;
  const ref = document.getElementById('doc-ref').value.trim();
  const party = document.getElementById('doc-party').value.trim();
  const amount = document.getElementById('doc-amount').value;
  const date = document.getElementById('doc-date').value;
  const notes = document.getElementById('doc-notes').value.trim();
  const fileInput = document.getElementById('doc-file');

  if (!type) { toast('Select a document type', 'error'); return; }

  const formData = new FormData();
  formData.append('doc_type', type);
  if (ref) formData.append('reference_number', ref);
  if (party) formData.append('party_name', party);
  if (amount) formData.append('amount', amount);
  if (date) formData.append('doc_date', date);
  if (notes) formData.append('notes', notes);
  if (fileInput.files[0]) formData.append('file', fileInput.files[0]);

  try {
    const res = await fetch('/api/documents', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
      body: formData
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new Error(data?.detail || 'Could not save record');

    ['doc-ref', 'doc-party', 'doc-amount', 'doc-date', 'doc-notes'].forEach(id => document.getElementById(id).value = '');
    fileInput.value = '';
    const msg = document.getElementById('doc-success');
    msg.textContent = '✓ Record saved'; msg.style.display = 'block';
    setTimeout(() => msg.style.display = 'none', 3000);
    toast('Record saved', 'ok');
    await loadDocuments();
  } catch (e) { toast(e.message, 'error'); }
}

async function viewDocument(id, filename) {
  try {
    const res = await fetch(`/api/documents/${id}/file`, { headers: { 'Authorization': `Bearer ${token}` } });
    if (!res.ok) throw new Error('Could not open file');
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.target = '_blank';
    a.rel = 'noopener';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 15000);
  } catch (e) { toast(e.message, 'error'); }
}

async function deleteDocument(id) {
  if (!confirm('Delete this record and its attached file?')) return;
  try {
    const res = await fetch(`/api/documents/${id}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (!res.ok && res.status !== 204) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail || 'Could not delete record');
    }
    toast('Record deleted', 'ok');
    await loadDocuments();
  } catch (e) { toast(e.message, 'error'); }
}

/* ── Analytics ───────────────────────────────────────────────────────────── */
async function loadAnalytics() {
  const days = document.getElementById('analytics-period')?.value || 30;
  let data;
  try { data = await apiFetch(`/api/ai/analytics?days=${days}`); } catch (e) { return; }
  if (!data) return;

  document.getElementById('kpi-revenue').textContent = fmt(data.total_revenue);
  document.getElementById('kpi-vat').textContent = fmt(data.total_vat_collected);
  document.getElementById('kpi-profit').textContent = fmt(data.gross_profit);
  document.getElementById('kpi-margin').textContent = data.profit_margin + '%';
  document.getElementById('kpi-sales').textContent = data.total_sales;

  // Revenue chart
  const labels = data.revenue_by_day.map(r => r.date);
  const values = data.revenue_by_day.map(r => r.revenue);
  if (revenueChart) revenueChart.destroy();
  const ctx = document.getElementById('revenue-chart').getContext('2d');
  revenueChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Revenue (KES)',
        data: values,
        borderColor: '#4f8ef7',
        backgroundColor: 'rgba(79,142,247,0.08)',
        borderWidth: 2,
        pointRadius: 2,
        fill: true,
        tension: 0.4,
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: '#6b7494', maxTicksLimit: 8 }, grid: { color: '#2a2f42' } },
        y: { ticks: { color: '#6b7494' }, grid: { color: '#2a2f42' } },
      }
    }
  });

  // Top products
  const maxRevenue = Math.max(...data.top_products.map(p => p.revenue), 1);
  document.getElementById('top-products-list').innerHTML = data.top_products.map(p => `
    <div class="top-product-row">
      <span class="top-product-name">${p.product_name}</span>
      <div class="top-product-bar"><div class="top-product-bar-fill" style="width:${(p.revenue/maxRevenue*100).toFixed(1)}%"></div></div>
      <span class="top-product-revenue">${fmt(p.revenue)}</span>
    </div>`).join('') || '<p style="color:var(--text-muted);font-size:.85rem">No sales yet</p>';
}

/* ── Alerts ──────────────────────────────────────────────────────────────── */
async function loadAlerts() {
  let alerts;
  try { alerts = await apiFetch('/api/ai/alerts') || []; } catch (e) { alerts = []; }
  const badge = document.getElementById('alert-badge');
  if (alerts.length > 0) { badge.textContent = alerts.length; badge.style.display = 'inline-block'; }
  else badge.style.display = 'none';

  document.getElementById('alerts-list').innerHTML = alerts.length
    ? alerts.map(a => `
      <div class="alert-card ${a.urgency}">
        <div>
          <div class="alert-name">${a.product_name}${a.sku ? ` <span style="color:var(--text-muted);font-size:.8rem">(${a.sku})</span>` : ''}</div>
          <div class="alert-detail">
            Stock: <strong>${a.current_stock} ${a.unit}</strong> · Reorder at: ${a.reorder_point} ${a.unit}
            ${a.days_until_stockout != null ? ` · ~${a.days_until_stockout} days left` : ''}
            · Reorder qty: ${a.reorder_quantity} ${a.unit}
          </div>
        </div>
        <span class="urgency-badge ${a.urgency}">${a.urgency.replace('_', ' ')}</span>
      </div>`).join('')
    : '<p style="color:var(--text-muted)">✓ All products are sufficiently stocked.</p>';
}

/* ── Forecast ────────────────────────────────────────────────────────────── */
async function loadForecast() {
  forecastProductId = document.getElementById('forecast-product-select').value;
  const days = document.getElementById('forecast-days').value;
  if (!forecastProductId) { toast('Select a product first', 'error'); return; }

  const data = await apiFetch(`/api/ai/forecast/${forecastProductId}?days_ahead=${days}`);
  if (!data) return;

  document.getElementById('forecast-result').style.display = 'block';
  document.getElementById('forecast-kpis').innerHTML = `
    <div class="kpi-card"><div class="kpi-label">Method</div><div class="kpi-value" style="font-size:1rem;text-transform:capitalize">${data.method.replace('_',' ')}</div></div>
    <div class="kpi-card"><div class="kpi-label">Data Points</div><div class="kpi-value">${data.data_points_used}</div></div>
    <div class="kpi-card"><div class="kpi-label">Suggested Reorder Point</div><div class="kpi-value">${data.suggested_reorder_point}</div></div>
    <div class="kpi-card"><div class="kpi-label">Suggested Reorder Qty</div><div class="kpi-value">${data.suggested_reorder_quantity}</div></div>
  `;

  const labels = data.forecast.map(f => f.date);
  const predicted = data.forecast.map(f => f.predicted_demand);
  const upper = data.forecast.map(f => f.upper_bound);
  const lower = data.forecast.map(f => f.lower_bound);

  if (forecastChart) forecastChart.destroy();
  const ctx = document.getElementById('forecast-chart').getContext('2d');
  forecastChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Predicted Demand',
          data: predicted,
          borderColor: '#4f8ef7',
          backgroundColor: 'rgba(79,142,247,0.1)',
          borderWidth: 2,
          tension: 0.4,
          fill: false,
        },
        {
          label: 'Upper Bound',
          data: upper,
          borderColor: 'rgba(45,206,137,0.3)',
          backgroundColor: 'rgba(45,206,137,0.05)',
          borderWidth: 1,
          borderDash: [4,4],
          tension: 0.4,
          fill: '+1',
          pointRadius: 0,
        },
        {
          label: 'Lower Bound',
          data: lower,
          borderColor: 'rgba(45,206,137,0.3)',
          backgroundColor: 'rgba(45,206,137,0.05)',
          borderWidth: 1,
          borderDash: [4,4],
          tension: 0.4,
          pointRadius: 0,
        },
      ]
    },
    options: {
      responsive: true,
      plugins: { legend: { labels: { color: '#6b7494' } } },
      scales: {
        x: { ticks: { color: '#6b7494', maxTicksLimit: 10 }, grid: { color: '#2a2f42' } },
        y: { ticks: { color: '#6b7494' }, grid: { color: '#2a2f42' } },
      }
    }
  });

  document.getElementById('forecast-apply-row').style.display = 'block';
  document.getElementById('forecast-apply-msg').textContent = '';
}

async function applyReorderSuggestion() {
  if (!forecastProductId) return;
  try {
    const res = await apiFetch(`/api/ai/reorder/${forecastProductId}/apply`, { method: 'POST' });
    document.getElementById('forecast-apply-msg').textContent = '✓ Reorder settings applied!';
    toast('Reorder settings updated', 'ok');
    await loadProducts();
  } catch (e) { toast(e.message, 'error'); }
}

/* ── Subscription / Licensing ────────────────────────────────────────────── */
async function loadLicenseStatus() {
  const box = document.getElementById('license-status-box');
  const banner = document.getElementById('license-banner');
  try {
    const res = await fetch('/api/license/status', { headers: { 'Authorization': `Bearer ${token}` } });
    const data = await res.json().catch(() => null);
    if (res.status === 404) {
      box.innerHTML = `<p style="color:var(--text-muted)">No license yet  renew to get started.</p>`;
      banner.style.display = 'none';
      return;
    }
    if (!res.ok) throw new Error(data?.detail || 'Could not load license status');

    const expired = data.status !== 'ACTIVE' || data.days_remaining <= 0;
    banner.style.display = expired ? 'block' : 'none';

    box.innerHTML = `
      <div class="form-group"><label>License Key</label>
        <input type="text" readonly value="${data.license_key}" onclick="this.select()" />
      </div>
      <div class="form-group"><label>Plan</label><div>${data.plan}</div></div>
      <div class="form-group"><label>Status</label>
        <span class="pill ${expired ? 'pill-out' : 'pill-ok'}">${expired ? 'Expired' : 'Active'}</span>
      </div>
      <div class="form-group"><label>Days Remaining</label><div>${data.days_remaining}</div></div>
      <div class="form-group"><label>Expires</label><div>${new Date(data.expires_at).toLocaleString()}</div></div>
    `;
  } catch (e) {
    box.innerHTML = `<p style="color:var(--red)">${e.message}</p>`;
  }
}

async function renewLicense() {
  try {
    const res = await fetch('/api/license/renew', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ plan: 'monthly' }),
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new Error(data?.detail || 'Renewal failed');
    const msg = document.getElementById('license-success');
    msg.textContent = `✓ Renewed! New key: ${data.license_key} (also emailed to you)`;
    msg.style.display = 'block';
    setTimeout(() => msg.style.display = 'none', 6000);
    toast('License renewed', 'ok');
    await loadLicenseStatus();
  } catch (e) {
    toast(e.message, 'error');
  }
}

/* ── Boot ────────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  const resetToken = new URLSearchParams(window.location.search).get('reset_token');
  if (resetToken) {
    showResetForm();
    return; // don't auto-login into the app while a reset is pending
  }
  if (token) initApp();
});
