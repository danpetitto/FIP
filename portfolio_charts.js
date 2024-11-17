document.addEventListener("DOMContentLoaded", function() {
    // Načtení dat pro graf hodnoty portfolia
    const chartDataElement = document.getElementById("chartData");
    if (!chartDataElement) {
        console.error("Element s ID 'chartData' nebyl nalezen.");
        return;
    }

    let chartData;
    try {
        chartData = JSON.parse(chartDataElement.textContent);
    } catch (e) {
        console.error("Chyba při parsování dat grafu:", e);
        return;
    }

    const dates = chartData.dates || [];
    const values = chartData.values || [];

    if (dates.length === 0 || values.length === 0) {
        console.error("Data pro graf nejsou platná.");
        return;
    }

    // Vykreslení grafu hodnoty portfolia v čase
    const ctxPortfolio = document.getElementById('portfolioChart').getContext('2d');
    new Chart(ctxPortfolio, {
        type: 'line',
        data: {
            labels: dates,
            datasets: [{
                label: 'Hodnota Portfolia v čase',
                data: values,
                borderColor: 'rgba(75, 192, 192, 1)',
                backgroundColor: 'rgba(75, 192, 192, 0.2)',
                fill: true
            }]
        },
        options: {
            responsive: true,
            scales: {
                x: { title: { display: true, text: 'Datum' } },
                y: { title: { display: true, text: 'Hodnota pozice' } }
            }
        }
    });
});
