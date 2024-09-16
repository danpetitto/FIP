document.addEventListener("DOMContentLoaded", function() {
    // Graf sektorů
    var ctxSector = document.getElementById('sectorInvestmentChart').getContext('2d');
    var sectorLabels = JSON.parse(document.getElementById('sectorChartLabels').textContent || '[]');
    var sectorData = JSON.parse(document.getElementById('sectorChartData').textContent || '[]');

    var backgroundColors = [
        'rgba(255, 99, 132, 0.2)', 'rgba(54, 162, 235, 0.2)', 'rgba(255, 206, 86, 0.2)', 
        'rgba(75, 192, 192, 0.2)', 'rgba(153, 102, 255, 0.2)', 'rgba(255, 159, 64, 0.2)',
        'rgba(199, 199, 199, 0.2)', 'rgba(255, 99, 71, 0.2)', 'rgba(144, 238, 144, 0.2)',
        'rgba(173, 216, 230, 0.2)'
    ];

    var borderColors = [
        'rgba(255, 99, 132, 1)', 'rgba(54, 162, 235, 1)', 'rgba(255, 206, 86, 1)', 
        'rgba(75, 192, 192, 1)', 'rgba(153, 102, 255, 1)', 'rgba(255, 159, 64, 1)',
        'rgba(199, 199, 199, 1)', 'rgba(255, 99, 71, 1)', 'rgba(144, 238, 144, 1)', 
        'rgba(173, 216, 230, 1)'
    ];

    // Vykreslení grafu sektorů
    var sectorInvestmentChart = new Chart(ctxSector, {
        type: 'pie',
        data: {
            labels: sectorLabels,
            datasets: [{
                label: 'Procento zainvestováno',
                data: sectorData,
                backgroundColor: backgroundColors.slice(0, sectorData.length),
                borderColor: borderColors.slice(0, sectorData.length),
                borderWidth: 1
            }]
        },
        options: {
            tooltips: {
                callbacks: {
                    label: function(tooltipItem, data) {
                        var label = data.labels[tooltipItem.index] || '';
                        var value = data.datasets[0].data[tooltipItem.index];
                        return label + ': ' + value.toFixed(2) + '%';
                    }
                }
            }
        }
    });

    // Graf jednotlivých akcií
    var ctxPosition = document.getElementById('positionInvestmentChart').getContext('2d');
    var positionLabels = JSON.parse(document.getElementById('positionChartLabels').textContent || '[]');
    var positionData = JSON.parse(document.getElementById('positionChartData').textContent || '[]');

    // Vykreslení grafu jednotlivých akcií
    var positionInvestmentChart = new Chart(ctxPosition, {
        type: 'pie',
        data: {
            labels: positionLabels,
            datasets: [{
                label: 'Procento zainvestováno do jednotlivých akcií',
                data: positionData,
                backgroundColor: backgroundColors.slice(0, positionData.length),
                borderColor: borderColors.slice(0, positionData.length),
                borderWidth: 1
            }]
        },
        options: {
            tooltips: {
                callbacks: {
                    label: function(tooltipItem, data) {
                        var label = data.labels[tooltipItem.index] || '';
                        var value = data.datasets[0].data[tooltipItem.index];
                        return label + ': ' + value.toFixed(2) + '%';
                    }
                }
            }
        }
    });
});
