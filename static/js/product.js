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
    if (!pills.length) return;

    pills.forEach(pill => {
        pill.addEventListener('click', () => {
            const parent = pill.parentElement;
            // Unselect sibling pills
            parent.querySelectorAll('.variant-pill').forEach(p => p.classList.remove('active'));
            pill.classList.add('active');

            updateVariantInfo();
        });
    });
}

// Fetch corresponding details for selected attributes
function updateVariantInfo() {
    const prodIdInput = document.getElementById('variant-product-id');
    if (!prodIdInput) return;
    const productId = prodIdInput.value;
    
    // Read currently active attributes
    const colorPill = document.querySelector('.variant-group[data-attr="color"] .variant-pill.active');
    const sizePill = document.querySelector('.variant-group[data-attr="size"] .variant-pill.active');
    const ramPill = document.querySelector('.variant-group[data-attr="ram"] .variant-pill.active');
    const storagePill = document.querySelector('.variant-group[data-attr="storage"] .variant-pill.active');

    const color = colorPill ? colorPill.getAttribute('data-val') : '';
    const size = sizePill ? sizePill.getAttribute('data-val') : '';
    const ram = ramPill ? ramPill.getAttribute('data-val') : '';
    const storage = storagePill ? storagePill.getAttribute('data-val') : '';

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
            const priceEl = document.getElementById('detail-offer-price');
            const stockEl = document.getElementById('detail-stock-count');
            const skuEl = document.getElementById('detail-sku');
            const addToCartBtn = document.getElementById('add-to-cart-btn');
            const variantIdInput = document.getElementById('selected-variant-id');
            const mainImg = document.getElementById('main-image-el');

            if (data.success) {
                // Update display price, stock status
                priceEl.textContent = `INR ${data.price.toFixed(2)}`;
                stockEl.textContent = `${data.stock} items remaining`;
                skuEl.textContent = `SKU: ${data.sku}`;
                variantIdInput.value = data.variant_id;

                if (data.stock > 0) {
                    addToCartBtn.disabled = false;
                    addToCartBtn.textContent = "Add to Cart";
                } else {
                    addToCartBtn.disabled = true;
                    addToCartBtn.textContent = "Out of Stock";
                }

                // If variant has specific image, swap main gallery image
                if (data.image_url) {
                    mainImg.src = data.image_url;
                } else if (data.image_path) {
                    mainImg.src = (data.image_path.startsWith('http') || data.image_path.startsWith('/')) ? data.image_path : `/static/uploads/${data.image_path}`;
                }
            } else {
                priceEl.textContent = "Unavailable";
                stockEl.textContent = "Selected variant options are out of stock";
                addToCartBtn.disabled = true;
                addToCartBtn.textContent = "Unavailable Selection";
                variantIdInput.value = "";
            }
        })
        .catch(err => console.error("Error updating variant details:", err));
}
