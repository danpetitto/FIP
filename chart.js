document.addEventListener("DOMContentLoaded", function() {
    // Vykreslení grafu investic do akcií
    var ctxInvestment = document.getElementById('investmentChart').getContext('2d');
    var labelsInvestment = JSON.parse(document.getElementById('chartLabels').textContent);
    var dataInvestment = JSON.parse(document.getElementById('chartData').textContent);

    var investmentChart = new Chart(ctxInvestment, {
        type: 'pie',
        data: {
            labels: labelsInvestment,
            datasets: [{
                label: 'Procento zainvestováno do akcií',
                data: dataInvestment,
                backgroundColor: [
                    'rgba(255, 99, 132, 0.2)',
                    'rgba(54, 162, 235, 0.2)',
                    'rgba(255, 206, 86, 0.2)',
                    'rgba(75, 192, 192, 0.2)',
                    'rgba(153, 102, 255, 0.2)',
                    'rgba(255, 159, 64, 0.2)'
                ],
                borderColor: [
                    'rgba(255, 99, 132, 1)',
                    'rgba(54, 162, 235, 1)',
                    'rgba(255, 206, 86, 1)',
                    'rgba(75, 192, 192, 1)',
                    'rgba(153, 102, 255, 1)',
                    'rgba(255, 159, 64, 1)'
                ],
                borderWidth: 1
            }]
        }
    });

    // Vykreslení grafu investic podle sektoru
    var ctxSector = document.getElementById('sectorChart').getContext('2d');
    var labelsSector = JSON.parse(document.getElementById('sectorLabels').textContent);
    var dataSector = JSON.parse(document.getElementById('sectorData').textContent);

    var sectorChart = new Chart(ctxSector, {
        type: 'pie',
        data: {
            labels: labelsSector,
            datasets: [{
                label: 'Procento zainvestováno podle sektoru',
                data: dataSector,
                backgroundColor: [
                    'rgba(255, 159, 64, 0.2)',
                    'rgba(153, 102, 255, 0.2)',
                    'rgba(75, 192, 192, 0.2)',
                    'rgba(255, 206, 86, 0.2)',
                    'rgba(54, 162, 235, 0.2)',
                    'rgba(255, 99, 132, 0.2)'
                ],
                borderColor: [
                    'rgba(255, 159, 64, 1)',
                    'rgba(153, 102, 255, 1)',
                    'rgba(75, 192, 192, 1)',
                    'rgba(255, 206, 86, 1)',
                    'rgba(54, 162, 235, 1)',
                    'rgba(255, 99, 132, 1)'
                ],
                borderWidth: 1
            }]
        }
    });
});
