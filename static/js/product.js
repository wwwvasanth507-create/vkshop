// Product Details features (variant selection, gallery swap, and image zoom lens magnifier)

document.addEventListener('DOMContentLoaded', () => {
    initGallery();
    initZoomEffect();
    initVariantSelector();
});

// Switch main image on thumbnail clicks
function initGallery() {
    const thumbs = document.querySelectorAll('.gallery-thumb');
    const mainImg = document.getElementById('main-image-el');
    if (!thumbs.length || !mainImg) return;

    thumbs.forEach(thumb => {
        thumb.addEventListener('click', () => {
            // Deactivate other thumbnails
            thumbs.forEach(t => t.classList.remove('active'));
            thumb.classList.add('active');
            
            // Swap source image
            const newSrc = thumb.getAttribute('data-large');
            mainImg.src = newSrc;
        });
    });
}

// Elegant CSS transition scale zoom on mouse hover
function initZoomEffect() {
    const mainImg = document.getElementById('main-image-el');
    if (!mainImg) return;

    mainImg.addEventListener('mousemove', (e) => {
        const { left, top, width, height } = mainImg.getBoundingClientRect();
        const x = ((e.clientX - left) / width) * 100;
        const y = ((e.clientY - top) / height) * 100;
        
        mainImg.style.transformOrigin = `${x}% ${y}%`;
        mainImg.style.transform = 'scale(1.8)';
    });

    mainImg.addEventListener('mouseleave', () => {
        mainImg.style.transform = 'scale(1)';
        mainImg.style.transformOrigin = 'center center';
    });
}

// Dynamic variant combinations selector
function initVariantSelector() {
    const pills = document.querySelectorAll('.variant-pill');
    const clearBtn = document.getElementById('clear-variant-selection');

    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            document.querySelectorAll('.variant-pill').forEach(p => p.classList.remove('active'));
            updateVariantInfo();
        });
    }

    if (!pills.length) return;

    pills.forEach(pill => {
        pill.addEventListener('click', () => {
            const parent = pill.parentElement;
            // Toggle active pill selection
            if (pill.classList.contains('active')) {
                pill.classList.remove('active');
            } else {
                parent.querySelectorAll('.variant-pill').forEach(p => p.classList.remove('active'));
                pill.classList.add('active');
            }

            updateVariantInfo();
        });
    });
}

// Fetch corresponding details for selected attributes or fall back to base product
function updateVariantInfo() {
    const prodIdInput = document.getElementById('variant-product-id');
    if (!prodIdInput) return;
    const productId = prodIdInput.value;
    
    const basePrice = prodIdInput.getAttribute('data-base-price');
    const baseStock = prodIdInput.getAttribute('data-base-stock');
    const baseSku = prodIdInput.getAttribute('data-base-sku');
    const baseImage = prodIdInput.getAttribute('data-base-image');

    const clearBtn = document.getElementById('clear-variant-selection');
    
    // Read currently active attributes
    const colorPill = document.querySelector('.variant-group[data-attr="color"] .variant-pill.active');
    const sizePill = document.querySelector('.variant-group[data-attr="size"] .variant-pill.active');
    const ramPill = document.querySelector('.variant-group[data-attr="ram"] .variant-pill.active');
    const storagePill = document.querySelector('.variant-group[data-attr="storage"] .variant-pill.active');

    const color = colorPill ? colorPill.getAttribute('data-val') : '';
    const size = sizePill ? sizePill.getAttribute('data-val') : '';
    const ram = ramPill ? ramPill.getAttribute('data-val') : '';
    const storage = storagePill ? storagePill.getAttribute('data-val') : '';

    const priceEl = document.getElementById('detail-offer-price');
    const stockEl = document.getElementById('detail-stock-count');
    const skuEl = document.getElementById('detail-sku');
    const addToCartBtn = document.getElementById('add-to-cart-btn');
    const variantIdInput = document.getElementById('selected-variant-id');
    const mainImg = document.getElementById('main-image-el');

    // If no attributes selected, show base product details
    if (!color && !size && !ram && !storage) {
        if (clearBtn) clearBtn.style.display = 'none';
        if (variantIdInput) variantIdInput.value = '';
        if (priceEl && basePrice) priceEl.textContent = `INR ${parseFloat(basePrice).toFixed(2)}`;
        if (skuEl && baseSku) skuEl.textContent = `SKU: ${baseSku}`;
        if (mainImg && baseImage) mainImg.src = baseImage;
        if (stockEl) {
            stockEl.innerHTML = '<span style="color: var(--success);"><i class="fa-solid fa-circle-check"></i> In Stock — Base product selected</span>';
        }
        if (addToCartBtn) {
            addToCartBtn.disabled = false;
            addToCartBtn.textContent = 'Add to Cart';
        }
        return;
    }

    if (clearBtn) clearBtn.style.display = 'inline-flex';

    const params = new URLSearchParams({
        product_id: productId,
        color: color,
        size: size,
        ram: ram,
        storage: storage
    });

    fetch(`/api/product-variant-details?${params.toString()}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                if (data.is_base) {
                    variantIdInput.value = '';
                    if (priceEl) priceEl.textContent = `INR ${data.price.toFixed(2)}`;
                    if (stockEl) stockEl.innerHTML = `<span style="color: var(--success);"><i class="fa-solid fa-circle-check"></i> In Stock — Base product selected</span>`;
                    if (skuEl) skuEl.textContent = `SKU: ${data.sku}`;
                    if (addToCartBtn) {
                        addToCartBtn.disabled = false;
                        addToCartBtn.textContent = 'Add to Cart';
                    }
                } else {
                    variantIdInput.value = data.variant_id;
                    if (priceEl) priceEl.textContent = `INR ${data.price.toFixed(2)}`;
                    if (skuEl) skuEl.textContent = `SKU: ${data.sku}`;
                    
                    if (data.stock > 0) {
                        if (stockEl) stockEl.innerHTML = `<span style="color: var(--success);"><i class="fa-solid fa-circle-check"></i> Variant In Stock (${data.stock} available)</span>`;
                        if (addToCartBtn) {
                            addToCartBtn.disabled = false;
                            addToCartBtn.textContent = 'Add to Cart';
                        }
                    } else {
                        if (stockEl) stockEl.innerHTML = `<span style="color: var(--danger);"><i class="fa-solid fa-circle-exclamation"></i> Variant Out of Stock</span>`;
                        if (addToCartBtn) {
                            addToCartBtn.disabled = true;
                            addToCartBtn.textContent = 'Variant Out of Stock';
                        }
                    }

                    if (data.image_url) {
                        mainImg.src = data.image_url;
                    }
                }
            } else {
                // If combination is not found, allow purchasing base product
                variantIdInput.value = '';
                if (stockEl) {
                    stockEl.innerHTML = `<span style="color: var(--warning);"><i class="fa-solid fa-circle-info"></i> Combination unavailable — base product selected</span>`;
                }
                if (priceEl && basePrice) priceEl.textContent = `INR ${parseFloat(basePrice).toFixed(2)}`;
                if (addToCartBtn) {
                    addToCartBtn.disabled = false;
                    addToCartBtn.textContent = 'Add to Cart (Base Product)';
                }
            }
        })
        .catch(err => console.error('Error updating variant details:', err));
}
