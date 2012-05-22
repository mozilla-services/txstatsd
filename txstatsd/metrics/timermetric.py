import json
import time

from twisted.web import resource

from txstatsd.metrics.histogrammetric import HistogramMetricReporter
from txstatsd.metrics.metermetric import MeterMetricReporter
from txstatsd.metrics.metric import Metric
from txstatsd.stats.uniformsample \
    import UniformSample


class TimerMetric(Metric):
    """
    A timer metric which aggregates timing durations and provides duration
    statistics, plus throughput statistics via L{MeterMetric}.
    """

    def __init__(self, connection, name, sample_rate=1):
        """Construct a metric that reports samples to the supplied
        C{connection}.

        @param connection: The connection endpoint representing
            the StatsD server.
        @param name: Indicates what is being instrumented.
        @param sample_rate: Restrict the number of samples sent
            to the StatsD server based on the supplied C{sample_rate}.
        """
        Metric.__init__(self, connection, name, sample_rate=sample_rate)

    def mark(self, duration):
        """Report this sample performed in duration (measured in seconds)."""
        self.send("%s|ms" % (duration * 1000))


class TimerResource(resource.Resource):
    isLeaf = True

    def __init__(self, reporter):
        resource.Resource.__init__(self)
        self.reporter = reporter

    def render_GET(self, request):
        result = dict(
            histogram=self.reporter.histogram.histogram(),
            max_value=self.reporter.max(),
            min_value=self.reporter.min())
        return json.dumps(result)


class TimerMetricReporter(object):
    """
    A timer metric which aggregates timing durations and provides duration
    statistics, plus throughput statistics via L{MeterMetricReporter}.
    """

    def __init__(self, name, wall_time_func=time.time, prefix=""):
        """Construct a metric we expect to be periodically updated.

        @param name: Indicates what is being instrumented.
        @param wall_time_func: Function for obtaining wall time.
        @param prefix: If present, a string to prepend to the message
            composed when C{report} is called.
        """
        self.name = name
        self.wall_time_func = wall_time_func

        if prefix:
            prefix += "."
        self.prefix = prefix

        sample = UniformSample(1028)
        self.histogram = HistogramMetricReporter(sample)
        # total number of values seen
        self.count = 0
        self.clear()

    def clear(self, timestamp=None):
        """Clears all recorded durations."""
        self.histogram.clear()
        if timestamp is None:
            timestamp = self.wall_time_func()
        self.last_time = float(timestamp)

    def rate(self, timestamp):
        """The number of values seen since last clear."""
        dt = (timestamp - self.last_time)
        if dt == 0:
            return 0
        return self.histogram.count / dt

    def max(self):
        """Returns the longest recorded duration."""
        return self.histogram.max()

    def min(self):
        """Returns the shortest recorded duration."""
        return self.histogram.min()

    def mean(self):
        """Returns the arithmetic mean of all recorded durations."""
        return self.histogram.mean()

    def std_dev(self):
        """Returns the standard deviation of all recorded durations."""
        return self.histogram.std_dev()

    def getResource(self):
        """Return an http resource to represent this."""
        return TimerResource(self)

    def percentiles(self, *percentiles):
        """
        Returns an array of durations at the given percentiles.

        @param percentiles: One or more percentiles.
        """
        return [percentile for percentile in
            self.histogram.percentiles(*percentiles)]

    def get_values(self):
        """Returns a list of all recorded durations in the timer's sample."""
        return [value for value in self.histogram.get_values()]

    def update(self, duration):
        """Adds a recorded duration.

        @param duration: The length of the duration in seconds.
        """
        self.count += 1
        if duration >= 0:
            self.histogram.update(duration)

    def tick(self):
        pass

    def report(self, timestamp):
        # median, 75, 95, 98, 99, 99.9 percentile
        percentiles = self.percentiles(0.5, 0.75, 0.95, 0.98, 0.99, 0.999)
        metrics = []
        items = {".min": self.min(),
                 ".max": self.max(),
                 ".mean": self.mean(),
                 ".stddev": self.std_dev(),
                 ".99percentile": percentiles[4],
                 ".999percentile": percentiles[5],
                 ".count": self.count,
                 ".rate": self.rate(timestamp),
            }
        for item, value in items.iteritems():
            metrics.append((self.prefix + self.name + item,
                            round(value, 6), timestamp))
        self.clear(timestamp)
        return metrics
