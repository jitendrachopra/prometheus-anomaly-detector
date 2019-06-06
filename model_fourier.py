import datetime
import logging
import pandas as pd
import numpy as np
from metric import Metric
from numpy import fft

# Set up logging
_LOGGER = logging.getLogger(__name__)


class MetricPredictor:
    """docstring for Predictor."""

    model_name = "Fourier"
    model_description = "Forecast value based on fourier analysis"
    model = None
    predicted_df = None
    metric = None

    def __init__(self, metric, rolling_data_window_size="10d"):
        self.metric = Metric(metric, rolling_data_window_size)

    def fourier_extrapolation(self, input_series, n_predict, n_harmonics):
        n = input_series.size
        t = np.arange(0, n)
        p = np.polyfit(t, input_series, 1)
        input_no_trend = input_series - p[0] * t
        frequency_domain = fft.fft(input_no_trend)
        frequencies = fft.fftfreq(n)
        indexes = np.arange(n).tolist()
        indexes.sort(key=lambda i: np.absolute(frequencies[i]))

        time_steps = np.arange(0, n + n_predict)
        restored_signal = np.zeros(time_steps.size)

        for i in indexes[: 1 + n_harmonics * 2]:
            amplitude = np.absolute(frequency_domain[i]) / n
            phase = np.angle(frequency_domain[i])
            restored_signal += amplitude * np.cos(2 * np.pi * frequencies[i] * time_steps + phase)

        return restored_signal + p[0] * time_steps

    def train(self, metric_data, prediction_duration=15):

        prediction_range = prediction_duration
        # convert incoming metric to Metric Object
        self.metric = self.metric + Metric(
            metric_data
        )  # because the rolling_data_window_size is set, this df should not bloat

        data = self.metric.metric_values
        vals = np.array(data["y"].tolist())
        print("Training Model .....")
        forecast_values = self.fourier_extrapolation(vals, prediction_range, 1)  # int(len(vals)/3))
        dataframe_cols = {}
        dataframe_cols["yhat"] = np.array(forecast_values)

        # find most recent timestamp from original data and extrapolate new timestamps
        _LOGGER.debug("Creating Dummy Timestamps.....")
        minimum_time = min(data["ds"])
        dataframe_cols["timestamp"] = pd.date_range(
            minimum_time, periods=len(forecast_values), freq="min"
        )

        # create dummy upper and lower bounds

        _LOGGER.debug("Computing Bounds .... ")

        upper_bound = np.array(
            [
                (
                    np.ma.average(
                        forecast_values[:i], weights=np.linspace(0, 1, num=len(forecast_values[:i]))
                    )
                    + (np.std(forecast_values[:i]) * 2)
                )
                for i in range(len(forecast_values))
            ]
        )
        upper_bound[0] = np.mean(forecast_values[0])  # to account for no std of a single value
        lower_bound = np.array(
            [
                (
                    np.ma.average(
                        forecast_values[:i], weights=np.linspace(0, 1, num=len(forecast_values[:i]))
                    )
                    - (np.std(forecast_values[:i]) * 2)
                )
                for i in range(len(forecast_values))
            ]
        )
        lower_bound[0] = np.mean(forecast_values[0])  # to account for no std of a single value
        dataframe_cols["yhat_upper"] = upper_bound
        dataframe_cols["yhat_lower"] = lower_bound

        # create series and index into predictions_dict
        _LOGGER.debug("Formatting Forecast to Pandas ..... ")

        forecast = pd.DataFrame(data=dataframe_cols)
        forecast = forecast.set_index("timestamp")

        self.predicted_df = forecast
        _LOGGER.debug(forecast)

    def predict_value(self, prediction_datetime):
        """
        This function returns the predicted value of the metric for the prediction_datetime
        """
        nearest_index = self.predicted_df.index.get_loc(prediction_datetime, method="nearest")
        return self.predicted_df.iloc[[nearest_index]]
