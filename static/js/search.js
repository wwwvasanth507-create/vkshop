// Advanced search system logic (autocomplete, voice, barcode & image search mocks)

document.addEventListener('DOMContentLoaded', () => {
    initAutocomplete();
    initVoiceSearch();
    initBarcodeSearch();
    initImageSearch();
});

// Autocomplete suggestions as user types in the main search bar
function initAutocomplete() {
    const searchInput = document.getElementById('search-input');
    const suggestionsBox = document.getElementById('search-suggestions');
    if (!searchInput || !suggestionsBox) return;

    searchInput.addEventListener('input', () => {
        const query = searchInput.value.trim();
        if (query.length < 2) {
            suggestionsBox.style.display = 'none';
            return;
        }

        fetch(`/api/search-suggestions?q=${encodeURIComponent(query)}`)
            .then(res => res.json())
            .then(data => {
                if (data.length === 0) {
                    suggestionsBox.style.display = 'none';
                    return;
                }

                suggestionsBox.innerHTML = '';
                data.forEach(item => {
                    const row = document.createElement('a');
                    row.href = `/product/${item.slug}`;
                    row.className = 'suggestion-item';
                    row.style.display = 'flex';
                    row.style.alignItems = 'center';
                    row.style.gap = '0.75rem';
                    row.style.padding = '0.5rem 0.75rem';
                    row.style.borderBottom = '1px solid var(--border-color)';
                    
                    row.innerHTML = `
                        <img src="/static/uploads/products/${item.image}" style="width: 32px; height: 32px; object-fit: contain; border-radius: 4px;">
                        <div>
                            <div style="font-weight: 600; font-size: 0.9rem; color: var(--text-primary);">${item.label}</div>
                            <div style="font-size: 0.8rem; color: var(--primary);">INR ${item.price.toFixed(2)}</div>
                        </div>
                    `;
                    suggestionsBox.appendChild(row);
                });

                suggestionsBox.style.display = 'block';
                suggestionsBox.style.position = 'absolute';
                suggestionsBox.style.top = '100%';
                suggestionsBox.style.left = '0';
                suggestionsBox.style.right = '0';
                suggestionsBox.style.backgroundColor = 'var(--bg-secondary)';
                suggestionsBox.style.border = '1px solid var(--border-color)';
                suggestionsBox.style.borderRadius = '0 0 var(--radius-lg) var(--radius-lg)';
                suggestionsBox.style.boxShadow = 'var(--shadow-lg)';
                suggestionsBox.style.zIndex = '150';
            })
            .catch(err => console.error("Suggestions error:", err));
    });

    // Hide suggestions box on click outside
    document.addEventListener('click', (e) => {
        if (!searchInput.contains(e.target) && !suggestionsBox.contains(e.target)) {
            suggestionsBox.style.display = 'none';
        }
    });
}

// Simulated Voice Search
function initVoiceSearch() {
    const voiceBtn = document.getElementById('voice-search-btn');
    const searchInput = document.getElementById('search-input');
    if (!voiceBtn || !searchInput) return;

    voiceBtn.addEventListener('click', () => {
        voiceBtn.style.color = 'var(--danger)';
        searchInput.placeholder = "Listening... Speak now";
        
        // Mock recognition feedback after 2 seconds
        setTimeout(() => {
            const speechQueries = ["Smartphones", "Wireless Earbuds", "Leather Jackets", "Men Running Shoes"];
            const randomPick = speechQueries[Math.floor(Math.random() * speechQueries.length)];
            
            searchInput.value = randomPick;
            searchInput.placeholder = "Search products, brands, and categories...";
            voiceBtn.style.color = 'var(--text-secondary)';
            
            // Trigger search submit form automatically
            const searchForm = document.getElementById('search-form');
            if (searchForm) searchForm.submit();
        }, 2200);
    });
}

// Simulated Barcode / QR Code Search
function initBarcodeSearch() {
    const barcodeBtn = document.getElementById('barcode-search-btn');
    if (!barcodeBtn) return;

    barcodeBtn.addEventListener('click', () => {
        // Trigger a mock file selector or immediate code scan
        const mockBarcode = prompt("Simulate Barcode / QR code scanning. Enter a barcode code (e.g. BARCODE-IPHONE15, QR-SNEAKER):");
        if (mockBarcode) {
            // In our system we direct to search route
            window.location.href = `/search?q=${encodeURIComponent(mockBarcode)}`;
        }
    });
}

// Simulated Image Search
function initImageSearch() {
    const imageBtn = document.getElementById('image-search-btn');
    if (!imageBtn) return;

    imageBtn.addEventListener('click', () => {
        const fileInput = document.createElement('input');
        fileInput.type = 'file';
        fileInput.accept = 'image/*';
        
        fileInput.addEventListener('change', () => {
            if (fileInput.files.length > 0) {
                alert("Image received! Extracting visual features to search for matches...");
                
                // Mocks visual tags
                const tags = ["shirt", "shoe", "gadget", "watch"];
                const tag = tags[Math.floor(Math.random() * tags.length)];
                
                // Redirect search
                window.location.href = `/search?q=${encodeURIComponent(tag)}`;
            }
        });
        
        fileInput.click();
    });
}
