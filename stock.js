// stock.js

document.addEventListener("DOMContentLoaded", function () {
    const ctx = document.getElementById("stockChart").getContext("2d");
    const priceTargetsCtx = document.getElementById("priceTargetsChart").getContext("2d");
    const selectElement = document.getElementById("time-period-select");
    let stockChart;  // Proměnná pro uložení instance grafu
    let priceTargetsChart;  // Proměnná pro graf cenových cílů

    // Funkce pro načtení dat pro graf ceny akcie
    async function loadChartData(ticker, period) {
        try {
            const response = await fetch(`/stock/stock_chart/${ticker}?period=${period}`);
            const data = await response.json();

            if (data.error) {
                console.error("Chyba při načítání dat: ", data.error);
                return;
            }

            // Pokud úspěšně načteme data, připravíme data pro graf
            const chartData = {
                labels: data.dates,
                datasets: [{
                    label: `Cena akcie ${ticker}`,
                    data: data.prices,
                    borderColor: 'rgba(63, 81, 181, 1)',
                    backgroundColor: createGradient(ctx, 'rgba(63, 81, 181, 0.6)', 'rgba(63, 81, 181, 0)'),
                    fill: true,
                    borderWidth: 3,
                    pointBackgroundColor: 'rgba(63, 81, 181, 1)',
                    pointBorderColor: '#fff',
                    pointRadius: 6,
                    pointHoverRadius: 10,
                    pointHoverBackgroundColor: 'rgba(255, 87, 34, 1)',
                    pointHoverBorderColor: 'rgba(220, 220, 220, 1)',
                    tension: 0.4 // Udělá graf hladší
                }]
            };

            // Pokud graf už existuje, aktualizujeme data, jinak vytvoříme nový graf
            if (stockChart) {
                stockChart.data = chartData;
                stockChart.update();
            } else {
                stockChart = new Chart(ctx, {
                    type: 'line',
                    data: chartData,
                    options: getChartOptions('Cena akcie', 'Datum', 'Cena (USD)')
                });
            }
        } catch (error) {
            console.error("Chyba při volání API: ", error);
        }
    }

    // Funkce pro načtení dat pro graf cenových cílů
    async function loadPriceTargetsData(ticker) {
        try {
            const response = await fetch(`/stock/price_targets/${ticker}`);
            const data = await response.json();

            if (data.error) {
                console.error("Chyba při načítání dat: ", data.error);
                return;
            }

            // Pokud úspěšně načteme data, připravíme data pro graf
            const chartData = {
                labels: ['Low', 'Average', 'High', 'Current'],
                datasets: [{
                    label: 'Cenové cíle analytiků',
                    data: [data.target_low, data.target_mean, data.target_high, data.current_price_analyst],
                    backgroundColor: [
                        'rgba(233, 30, 99, 0.7)',  // Low
                        'rgba(3, 169, 244, 0.7)',  // Average
                        'rgba(76, 175, 80, 0.7)',  // High
                        'rgba(255, 193, 7, 0.8)'   // Current
                    ],
                    borderColor: [
                        'rgba(233, 30, 99, 1)',
                        'rgba(3, 169, 244, 1)',
                        'rgba(76, 175, 80, 1)',
                        'rgba(255, 193, 7, 1)'
                    ],
                    borderWidth: 1,
                    barThickness: 35,  // Zvětšení šířky sloupců
                    borderRadius: 10   // Zaoblené rohy sloupců
                }]
            };

            // Pokud graf už existuje, aktualizujeme data, jinak vytvoříme nový graf
            if (priceTargetsChart) {
                priceTargetsChart.data = chartData;
                priceTargetsChart.update();
            } else {
                priceTargetsChart = new Chart(priceTargetsCtx, {
                    type: 'bar',
                    data: chartData,
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                display: false
                            },
                            tooltip: {
                                callbacks: {
                                    label: function (context) {
                                        let label = context.dataset.label || '';
                                        if (label) {
                                            label += ': ';
                                        }
                                        label += `${context.parsed.y} USD`;
                                        return label;
                                    }
                                },
                                backgroundColor: 'rgba(0, 0, 0, 0.8)',
                                titleColor: '#fff',
                                bodyColor: '#fff'
                            }
                        },
                        scales: {
                            x: {
                                title: {
                                    display: true,
                                    text: 'Typ cíle',
                                    color: '#333',
                                    font: {
                                        family: 'Roboto',
                                        size: 16,
                                        weight: 'bold',
                                    }
                                },
                                grid: {
                                    display: false
                                }
                            },
                            y: {
                                title: {
                                    display: true,
                                    text: 'Cena (USD)',
                                    color: '#333',
                                    font: {
                                        family: 'Roboto',
                                        size: 16,
                                        weight: 'bold',
                                    }
                                },
                                grid: {
                                    color: 'rgba(200, 200, 200, 0.2)'
                                },
                                beginAtZero: true
                            }
                        }
                    }
                });
            }

        } catch (error) {
            console.error("Chyba při volání API: ", error);
        }
    }

    // Funkce pro vytvoření gradientu pozadí
    function createGradient(ctx, colorStart, colorEnd) {
        const gradient = ctx.createLinearGradient(0, 0, 0, 400);
        gradient.addColorStop(0, colorStart);
        gradient.addColorStop(1, colorEnd);
        return gradient;
    }

    // Funkce pro nastavení možností grafu
    function getChartOptions(title, xLabel, yLabel) {
        return {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    labels: {
                        color: '#444',
                        font: {
                            family: 'Roboto',
                            size: 16,
                            weight: 'bold',
                        }
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    titleColor: '#fff',
                    bodyColor: '#fff',
                    bodyFont: {
                        family: 'Roboto',
                        size: 14,
                    }
                }
            },
            scales: {
                x: {
                    title: {
                        display: true,
                        text: xLabel,
                        color: '#333',
                        font: {
                            family: 'Roboto',
                            size: 16,
                            weight: 'bold',
                        }
                    },
                    grid: {
                        display: false
                    }
                },
                y: {
                    title: {
                        display: true,
                        text: yLabel,
                        color: '#333',
                        font: {
                            family: 'Roboto',
                            size: 16,
                            weight: 'bold',
                        }
                    },
                    grid: {
                        color: 'rgba(200, 200, 200, 0.2)'
                    }
                }
            }
        };
    }

    // Inicializace grafu s výchozím časovým obdobím
    const ticker = window.location.pathname.split("/").pop();  // Předpokládáme, že ticker je v URL
    loadChartData(ticker, selectElement.value);
    loadPriceTargetsData(ticker);

    // Přepnutí časového období při změně výběru
    selectElement.addEventListener("change", function () {
        loadChartData(ticker, selectElement.value);
    });
});

