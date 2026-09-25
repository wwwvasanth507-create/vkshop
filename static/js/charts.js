class CanvasCharts {
    static getPixelRatio(ctx) {
        const dpr = window.devicePixelRatio || 1;
        const bsr = ctx.webkitBackingStorePixelRatio ||
                    ctx.mozBackingStorePixelRatio ||
                    ctx.msBackingStorePixelRatio ||
                    ctx.oBackingStorePixelRatio ||
                    ctx.backingStorePixelRatio || 1;
        return dpr / bsr;
    }

    static setupCanvas(canvas) {
        const rect = canvas.getBoundingClientRect();
        const ctx = canvas.getContext('2d');
        const ratio = this.getPixelRatio(ctx);
        
        canvas.width = rect.width * ratio;
        canvas.height = rect.height * ratio;
        canvas.style.width = rect.width + 'px';
        canvas.style.height = rect.height + 'px';
        
        ctx.scale(ratio, ratio);
        return ctx;
    }

    static drawBarChart(canvasId, labels, data, title, barColor = '#2563eb') {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;
        
        const ctx = this.setupCanvas(canvas);
        const width = canvas.getBoundingClientRect().width;
        const height = canvas.getBoundingClientRect().height;
        
        ctx.clearRect(0, 0, width, height);
        
        // Settings
        const padding = 50;
        const chartWidth = width - 2 * padding;
        const chartHeight = height - 2 * padding;
        
        // Draw title
        ctx.font = 'bold 14px Outfit, sans-serif';
        ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--text-primary').trim() || '#0f172a';
        ctx.textAlign = 'center';
        ctx.fillText(title, width / 2, 25);
        
        if (data.length === 0) {
            ctx.font = '12px Inter';
            ctx.fillText("No data available", width / 2, height / 2);
            return;
        }
        
        const maxVal = Math.max(...data) * 1.1 || 10;
        const barWidth = (chartWidth / data.length) * 0.6;
        const spacing = (chartWidth / data.length) * 0.4;
        
        // Draw grid & axes
        ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue('--border-color').trim() || '#e2e8f0';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(padding, padding);
        ctx.lineTo(padding, height - padding);
        ctx.lineTo(width - padding, height - padding);
        ctx.stroke();
        
        // Y Axis scale ticks
        ctx.font = '10px Inter';
        ctx.textAlign = 'right';
        ctx.fillStyle = '#94a3b8';
        const ticksCount = 5;
        for (let i = 0; i <= ticksCount; i++) {
            const val = ((maxVal / ticksCount) * i).toFixed(0);
            const y = height - padding - ((chartHeight / ticksCount) * i);
            ctx.fillText(val, padding - 10, y + 3);
            
            // Grid lines
            ctx.beginPath();
            ctx.moveTo(padding, y);
            ctx.lineTo(width - padding, y);
            ctx.stroke();
        }
        
        // Draw bars
        ctx.textAlign = 'center';
        for (let i = 0; i < data.length; i++) {
            const val = data[i];
            const barHeight = (val / maxVal) * chartHeight;
            const x = padding + spacing / 2 + i * (barWidth + spacing);
            const y = height - padding - barHeight;
            
            // Draw single bar
            ctx.fillStyle = barColor;
            ctx.beginPath();
            if (ctx.roundRect) {
                ctx.roundRect(x, y, barWidth, barHeight, [4, 4, 0, 0]);
            } else {
                ctx.rect(x, y, barWidth, barHeight);
            }
            ctx.fill();
            
            // Value text
            ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--text-secondary').trim() || '#475569';
            ctx.fillText(val.toFixed(0), x + barWidth / 2, y - 5);
            
            // Label
            ctx.fillText(labels[i], x + barWidth / 2, height - padding + 18);
        }
    }

    static drawLineChart(canvasId, labels, data, title, strokeColor = '#10b981', fillColor = 'rgba(16, 185, 129, 0.15)') {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;
        
        const ctx = this.setupCanvas(canvas);
        const width = canvas.getBoundingClientRect().width;
        const height = canvas.getBoundingClientRect().height;
        
        ctx.clearRect(0, 0, width, height);
        
        const padding = 50;
        const chartWidth = width - 2 * padding;
        const chartHeight = height - 2 * padding;
        
        // Draw title
        ctx.font = 'bold 14px Outfit, sans-serif';
        ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--text-primary').trim() || '#0f172a';
        ctx.textAlign = 'center';
        ctx.fillText(title, width / 2, 25);
        
        if (data.length === 0) {
            ctx.font = '12px Inter';
            ctx.fillText("No data available", width / 2, height / 2);
            return;
        }
        
        const maxVal = Math.max(...data) * 1.15 || 10;
        const stepX = chartWidth / (data.length - 1 || 1);
        
        // Grid & axes
        ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue('--border-color').trim() || '#e2e8f0';
        ctx.lineWidth = 1;
        
        // Ticks & Y-grid
        ctx.font = '10px Inter';
        ctx.textAlign = 'right';
        ctx.fillStyle = '#94a3b8';
        const ticksCount = 5;
        for (let i = 0; i <= ticksCount; i++) {
            const val = ((maxVal / ticksCount) * i).toFixed(0);
            const y = height - padding - ((chartHeight / ticksCount) * i);
            ctx.fillText(val, padding - 10, y + 3);
            
            ctx.beginPath();
            ctx.moveTo(padding, y);
            ctx.lineTo(width - padding, y);
            ctx.stroke();
        }
        
        // Draw line & gradient area
        ctx.beginPath();
        const points = [];
        for (let i = 0; i < data.length; i++) {
            const x = padding + i * stepX;
            const y = height - padding - ((data[i] / maxVal) * chartHeight);
            points.push({ x, y });
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        
        ctx.strokeStyle = strokeColor;
        ctx.lineWidth = 3;
        ctx.stroke();
        
        // Draw fill area
        if (points.length > 0) {
            ctx.lineTo(points[points.length - 1].x, height - padding);
            ctx.lineTo(points[0].x, height - padding);
            ctx.closePath();
            ctx.fillStyle = fillColor;
            ctx.fill();
        }
        
        // Draw data points circles and labels
        ctx.textAlign = 'center';
        ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--text-secondary').trim() || '#475569';
        for (let i = 0; i < points.length; i++) {
            const pt = points[i];
            
            // Circle dot
            ctx.beginPath();
            ctx.arc(pt.x, pt.y, 4, 0, 2 * Math.PI);
            ctx.fillStyle = strokeColor;
            ctx.fill();
            
            // Value text
            ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--text-primary').trim() || '#0f172a';
            ctx.fillText(data[i].toFixed(0), pt.x, pt.y - 8);
            
            // Label
            ctx.fillStyle = '#94a3b8';
            ctx.fillText(labels[i], pt.x, height - padding + 18);
        }
    }

    static drawPieChart(canvasId, labels, data, title) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;
        
        const ctx = this.setupCanvas(canvas);
        const width = canvas.getBoundingClientRect().width;
        const height = canvas.getBoundingClientRect().height;
        
        ctx.clearRect(0, 0, width, height);
        
        const total = data.reduce((a, b) => a + b, 0);
        const colors = ['#2563eb', '#10b981', '#f59e0b', '#ef4444', '#0ea5e9', '#8b5cf6'];
        
        // Draw title
        ctx.font = 'bold 14px Outfit, sans-serif';
        ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--text-primary').trim() || '#0f172a';
        ctx.textAlign = 'center';
        ctx.fillText(title, width / 2, 25);
        
        if (total === 0) {
            ctx.font = '12px Inter';
            ctx.fillText("No data available", width / 2, height / 2);
            return;
        }
        
        const centerX = width * 0.4;
        const centerY = height * 0.55;
        const radius = Math.min(width, height) * 0.3;
        
        let startAngle = 0;
        
        for (let i = 0; i < data.length; i++) {
            const sliceAngle = (data[i] / total) * 2 * Math.PI;
            ctx.beginPath();
            ctx.moveTo(centerX, centerY);
            ctx.arc(centerX, centerY, radius, startAngle, startAngle + sliceAngle);
            ctx.fillStyle = colors[i % colors.length];
            ctx.fill();
            startAngle += sliceAngle;
            
            // Draw Legend item
            const legendX = width * 0.75;
            const legendY = 60 + i * 25;
            
            ctx.beginPath();
            ctx.rect(legendX, legendY, 12, 12);
            ctx.fillStyle = colors[i % colors.length];
            ctx.fill();
            
            ctx.font = '11px Inter';
            ctx.textAlign = 'left';
            ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--text-secondary').trim() || '#475569';
            const percentage = ((data[i] / total) * 100).toFixed(0);
            ctx.fillText(`${labels[i]} (${percentage}%)`, legendX + 18, legendY + 10);
        }
    }
}
