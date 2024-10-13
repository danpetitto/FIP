document.addEventListener("DOMContentLoaded", function () {
    const ctx = document.getElementById("stockChart").getContext("2d");
    const enlargedCtx = document.getElementById("enlargedStockChart").getContext("2d");
    const selectElement = document.getElementById("time-period-select");
    let stockChart;  // Proměnná pro uložení instance grafu

    // Funkce pro načtení dat pro graf
    async function loadChartData(ticker, period) {
        try {
            const response = await fetch(`/stock/stock_chart/${ticker}?period=${period}`);
            const data = await response.json();

            if (data.error) {
                console.error("Chyba při načítání dat: ", data.error);
                return;
            }

            // Pokud úspěšně načteme data, vytvoříme graf
            const chartData = {
                labels: data.dates,
                datasets: [{
                    label: `Cena akcie ${ticker}`,
                    data: data.prices,
                    borderColor: 'rgba(75, 192, 192, 1)',
                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                    fill: true,
                    borderWidth: 1,
                }]
            };

            // Zničení předchozí instance grafu, pokud existuje
            if (stockChart) {
                stockChart.destroy();
            }

            // Vytvoření nového grafu
            stockChart = new Chart(ctx, {
                type: 'line',
                data: chartData,
                options: {
                    scales: {
                        x: {
                            display: true,
                            title: {
                                display: true,
                                text: 'Datum'
                            }
                        },
                        y: {
                            display: true,
                            title: {
                                display: true,
                                text: 'Cena (USD)'
                            }
                        }
                    }
                }
            });

            // Vytvoření zvětšeného grafu
            new Chart(enlargedCtx, {
                type: 'line',
                data: chartData,
                options: {
                    scales: {
                        x: {
                            display: true,
                            title: {
                                display: true,
                                text: 'Datum'
                            }
                        },
                        y: {
                            display: true,
                            title: {
                                display: true,
                                text: 'Cena (USD)'
                            }
                        }
                    }
                }
            });

        } catch (error) {
            console.error("Chyba při volání API: ", error);
        }
    }

    // Inicializace grafu s výchozím časovým obdobím
    const ticker = window.location.pathname.split("/").pop();  // Předpokládáme, že ticker je v URL
    loadChartData(ticker, selectElement.value);

    // Přepnutí časového období při změně výběru
    selectElement.addEventListener("change", function () {
        loadChartData(ticker, selectElement.value);
    });
});
