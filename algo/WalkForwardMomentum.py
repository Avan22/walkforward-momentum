from AlgorithmImports import *

class WalkForwardMomentum(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2018, 1, 1)
        self.SetEndDate(2020, 1, 1)
        self.SetCash(100000)
        self.symbol = self.AddEquity("SPY", Resolution.Daily).Symbol
        self.SetWarmUp(30, Resolution.Daily)
        self.equity_chart = Chart("Strategy Equity")
        self.equity_chart.AddSeries(Series("Equity", SeriesType.Line, 0))
        self.AddChart(self.equity_chart)

    def OnData(self, data: Slice):
        if self.IsWarmingUp:
            return
        self.Plot("Strategy Equity", "Equity", float(self.Portfolio.TotalPortfolioValue))
        if not self.Portfolio.Invested:
            self.SetHoldings(self.symbol, 1.0)
