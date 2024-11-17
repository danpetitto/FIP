document.addEventListener("DOMContentLoaded", function () {
    // Definice barev, použitelné pro všechny grafy
    const backgroundColors = [
        'rgba(54, 162, 235, 0.6)', 'rgba(255, 99, 132, 0.6)',
        'rgba(75, 192, 192, 0.6)', 'rgba(255, 206, 86, 0.6)',
        'rgba(153, 102, 255, 0.6)', 'rgba(255, 159, 64, 0.6)',
        'rgba(199, 199, 199, 0.6)'
    ];

    const borderColors = [
        'rgba(54, 162, 235, 1)', 'rgba(255, 99, 132, 1)',
        'rgba(75, 192, 192, 1)', 'rgba(255, 206, 86, 1)',
        'rgba(153, 102, 255, 1)', 'rgba(255, 159, 64, 1)',
        'rgba(199, 199, 199, 1)'
    ];

    // Přidání sloupcového grafu pro Top Investice
    const ctxTopInvestment = document.getElementById('topInvestmentChart');
    if (ctxTopInvestment) {
        const ctxTopInvestmentContext = ctxTopInvestment.getContext('2d');
        const topInvestmentLabelsElement = document.getElementById('topInvestmentLabels');
        const topInvestmentProfitsElement = document.getElementById('topInvestmentProfits');

        if (topInvestmentLabelsElement && topInvestmentProfitsElement) {
            const topInvestmentLabels = JSON.parse(topInvestmentLabelsElement.textContent || '[]');
            const topInvestmentProfits = JSON.parse(topInvestmentProfitsElement.textContent || '[]');

            new Chart(ctxTopInvestmentContext, {
                type: 'bar',
                data: {
                    labels: topInvestmentLabels,
                    datasets: [{
                        label: 'Profit (€)',
                        data: topInvestmentProfits,
                        backgroundColor: backgroundColors.slice(0, topInvestmentLabels.length),
                        borderColor: borderColors.slice(0, topInvestmentLabels.length),
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true
                        }
                    }
                }
            });
        }
    }

    // Allocation Chart - Koláčový graf alokace podle akcií
    const stockLabelsElement = document.getElementById('stockLabelsData');
    const stockPercentagesElement = document.getElementById('stockPercentagesData');

    if (stockLabelsElement && stockPercentagesElement) {
        try {
            const stockLabels = JSON.parse(stockLabelsElement.textContent || '[]');
            const stockPercentages = JSON.parse(stockPercentagesElement.textContent || '[]');

            if (stockLabels.length > 0 && stockPercentages.length > 0) {
                const ctxAllocation = document.getElementById('allocationChart');

                if (ctxAllocation) {
                    const ctxAllocationContext = ctxAllocation.getContext('2d');

                    new Chart(ctxAllocationContext, {
                        type: 'pie',
                        data: {
                            labels: stockLabels,
                            datasets: [{
                                label: 'Alokace podle akcií (%)',
                                data: stockPercentages,
                                backgroundColor: backgroundColors.slice(0, stockLabels.length),
                                borderColor: borderColors.slice(0, stockLabels.length),
                                borderWidth: 1
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            animation: {
                                duration: 1000,
                                easing: 'easeOutBounce'
                            }
                        }
                    });
                } else {
                    console.error("Element canvas s id 'allocationChart' nebyl nalezen.");
                }
            } else {
                console.warn("Data pro graf alokace podle akcií nejsou dostupná nebo jsou prázdná.");
            }
        } catch (error) {
            console.error("Chyba při parsování JSON dat pro alokaci podle akcií: ", error);
        }
    }

    // Country Allocation Chart - Koláčový graf alokace podle zemí
    const countryLabelsElement = document.getElementById('countryLabelsData');
    const countryPercentagesElement = document.getElementById('countryPercentagesData');

    if (countryLabelsElement && countryPercentagesElement) {
        try {
            const countryLabels = JSON.parse(countryLabelsElement.textContent || '[]');
            const countryPercentages = JSON.parse(countryPercentagesElement.textContent || '[]');

            if (countryLabels.length > 0 && countryPercentages.length > 0) {
                const ctxCountryAllocation = document.getElementById('countryAllocationChart');

                if (ctxCountryAllocation) {
                    const ctxCountryAllocationContext = ctxCountryAllocation.getContext('2d');

                    new Chart(ctxCountryAllocationContext, {
                        type: 'pie',
                        data: {
                            labels: countryLabels,
                            datasets: [{
                                label: 'Alokace podle zemí (%)',
                                data: countryPercentages,
                                backgroundColor: backgroundColors.slice(0, countryLabels.length),
                                borderColor: borderColors.slice(0, countryLabels.length),
                                borderWidth: 1
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            animation: {
                                duration: 1000,
                                easing: 'easeOutBounce'
                            }
                        }
                    });
                } else {
                    console.error("Element canvas s id 'countryAllocationChart' nebyl nalezen.");
                }
            } else {
                console.warn("Data pro graf alokace podle zemí nejsou dostupná nebo jsou prázdná.");
            }
        } catch (error) {
            console.error("Chyba při parsování JSON dat pro alokaci podle zemí: ", error);
        }
    }
}); // Správné uzavření `DOMContentLoaded` listeneru


// Sector Allocation Chart - Koláčový graf alokace podle sektorů
document.addEventListener('DOMContentLoaded', function () {
    const sectorLabelsElement = document.getElementById('sectorLabelsData');
    const sectorPercentagesElement = document.getElementById('sectorPercentagesData');

    if (sectorLabelsElement && sectorPercentagesElement) {
        try {
            const sectorLabels = JSON.parse(sectorLabelsElement.textContent || '[]');
            const sectorPercentages = JSON.parse(sectorPercentagesElement.textContent || '[]');

            console.log("DEBUG: Sector Labels:", sectorLabels);
            console.log("DEBUG: Sector Percentages:", sectorPercentages);

            if (sectorLabels.length > 0 && sectorPercentages.length > 0) {
                const ctxSectorAllocation = document.getElementById('sectorAllocationChart');

                if (ctxSectorAllocation) {
                    const ctxSectorAllocationContext = ctxSectorAllocation.getContext('2d');

                    new Chart(ctxSectorAllocationContext, {
                        type: 'pie',
                        data: {
                            labels: sectorLabels,
                            datasets: [{
                                label: 'Alokace podle sektorů (%)',
                                data: sectorPercentages,
                                backgroundColor: generateBackgroundColors(sectorLabels.length),
                                borderColor: generateBorderColors(sectorLabels.length),
                                borderWidth: 1
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            animation: {
                                duration: 1000,
                                easing: 'easeOutBounce'
                            }
                        }
                    });
                } else {
                    console.error("Element canvas s id 'sectorAllocationChart' nebyl nalezen.");
                }
            } else {
                console.warn("Data pro graf alokace podle sektorů nejsou dostupná nebo jsou prázdná.");
            }
        } catch (error) {
            console.error("Chyba při parsování JSON dat pro alokaci podle sektorů: ", error);
        }
    } else {
        console.error("Elementy pro načtení dat o sektorech nebyly nalezeny.");
    }
});

// Funkce pro generování barev pro graf
function generateBackgroundColors(count) {
    const colors = [
        'rgba(255, 99, 132, 0.2)',
        'rgba(54, 162, 235, 0.2)',
        'rgba(255, 206, 86, 0.2)',
        'rgba(75, 192, 192, 0.2)',
        'rgba(153, 102, 255, 0.2)',
        'rgba(255, 159, 64, 0.2)'
    ];
    return Array(count).fill().map((_, i) => colors[i % colors.length]);
}

function generateBorderColors(count) {
    const colors = [
        'rgba(255, 99, 132, 1)',
        'rgba(54, 162, 235, 1)',
        'rgba(255, 206, 86, 1)',
        'rgba(75, 192, 192, 1)',
        'rgba(153, 102, 255, 1)',
        'rgba(255, 159, 64, 1)'
    ];
    return Array(count).fill().map((_, i) => colors[i % colors.length]);
}
