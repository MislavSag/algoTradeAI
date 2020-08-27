import glob
import os
import numpy as np
import pandas as pd
from numba import njit, prange
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib import pyplot
from mlfinlab.structural_breaks import (
    get_chu_stinchcombe_white_statistics,
    get_chow_type_stat, get_sadf)
import mlfinlab as ml
import mlfinlab.microstructural_features as micro
import trademl as tml
from trademl.modeling.utils import time_method



### PANDAS OPTIONS
pd.set_option('display.max_rows', 500)
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)


### HYPERPARAMETERS
save_path = 'D:/market_data/usa/ohlcv_features'
add_ta = False
ta_periods = [5, 30, 480, 960, 2400, 4800, 9600]
add_labels = False
env_directory = None  # os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
median_outlier_thrteshold = 25


### IMPORT DATA
# import data from mysql database and 
contract = 'SPY'
q = 'SELECT date, open, high, low, close, volume FROM SPY'
data = tml.modeling.utils.query_to_db(q, 'odvjet12_market_data_usa')
data.set_index(data.date, inplace=True)
data.drop(columns=['date'], inplace=True)
data.sort_index(inplace=True)


### REMOVE OUTLIERS
print(data.shape)
data = tml.modeling.outliers.remove_ourlier_diff_median(data, median_outlier_thrteshold)
print(data.shape)
    

### STATIONARITY
# save original ohlcv, I will need it later
ohlc = data[['open', 'high', 'low', 'close']]
ohlc.columns = ['open_orig', 'high_orig', 'low_orig', 'close_orig']


df1 = data['close'].resample('1D').last()
df1.dropna(inplace=True)
df1 = df1.squeeze()


x = df1.values
d = 0.2
thres = 1e-4
lim = len(x)


@numba.njit
def _frac_diff_ffd(x, d, lim, thres=_default_thresh):
    """d is any positive real"""
    w = get_weights_ffd(d, thres, lim)
    width = len(w) - 1
    output = []
    # output.extend([np.nan] * width) # the first few entries *were* zero, should be nan?
    # output.extend(np.repeat([np.nan], 3)) # the first few entries *were* zero, should be nan?
    # output = [np.nan for i in range(width)]
    for i in range(0, x.shape[0]):
        if i < width:
            output.append(np.nan)
        else:
            output.append(np.dot(w.T, x[i - width: i + 1])[0])
    # output = np.vstack(output).reshape(-1)
    # output - np.array(output, dtype=float)
    return w, output


test, test1 = _frac_diff_ffd(x, d, lim, thres)
test1.shape


# get dmin for every column
stationaryCols, min_d = tml.modeling.stationarity.min_ffd_all_cols(data)
stationaryCols, min_d = min_ffd_all_cols(data)

# save to github for later 
min_dmin_d_save_for_backtesting = pd.Series(0, index=data.columns)
min_dmin_d_save_for_backtesting.update(min_d)
min_dmin_d_save_for_backtesting.dropna(inplace=True)
min_dmin_d_save_for_backtesting.to_csv(
    'C:/Users/Mislav/Documents/GitHub/trademl/data/min_d_' + contract + '.csv', sep=';')

# convert unstationary to stationary
data = tml.modeling.stationarity.unstat_cols_to_stat(data, min_d, stationaryCols)  # tml.modeling.stationarity.unstat_cols_to_stat
data.dropna(inplace=True)

# merge orig ohlc to spyStat
data = data.merge(ohlc, how='left', left_index=True, right_index=True)



########### TEST ##############
# data_sample = data.iloc[:20000]
# periods = [5, 30, 60, 480, 960, 2400, 4800, 9600]
# data_sample = tml.modeling.features.add_technical_indicators(data_sample, periods=periods)
# data_sample.columns = [cl[0] if isinstance(cl, tuple) else cl for cl in data_sample.columns]
# data_sample.isna().sum().sort_values()
########### TEST ##############


### 1) ADD FEATURES
# add technical indicators
if add_ta:
    # periods = [5, 30, 480, 960, 2400, 4800, 9600]
    data = tml.modeling.features.add_technical_indicators(data, periods=ta_periods)
    data.columns = [cl[0] if isinstance(cl, tuple) else cl for cl in data.columns]

# add ohlc transformations
data['high_low'] = data['high'] - data['low']
data['close_open'] = data['close'] - data['open']
data['close_ath'] = data['close'].cummax()

# simple momentum
data['momentum1'] = data['close'].pct_change(periods=1)
data['momentum2'] = data['close'].pct_change(periods=2)
data['momentum3'] = data['close'].pct_change(periods=3)
data['momentum4'] = data['close'].pct_change(periods=4)
data['momentum5'] = data['close'].pct_change(periods=5)

# Volatility
data['volatility_60'] = np.log(data['close']).diff().rolling(
    window=60, min_periods=60, center=False).std()
data['volatility_30'] = np.log(data['close']).diff().rolling(
    window=30, min_periods=30, center=False).std()
data['volatility_15'] = np.log(data['close']).diff().rolling(
    window=15, min_periods=15, center=False).std()
data['volatility_10'] = np.log(data['close']).diff().rolling(
    window=10, min_periods=10, center=False).std()
data['volatility_5'] =np.log(data['close']).diff().rolling(
    window=5, min_periods=5, center=False).std()

# Skewness
data['skew_60'] = np.log(data['close']).diff().rolling(
    window=60, min_periods=60, center=False).skew()
data['skew_30'] = np.log(data['close']).diff().rolling(
    window=30, min_periods=30, center=False).skew()
data['skew_15'] = np.log(data['close']).diff().rolling(
    window=15, min_periods=15, center=False).skew()
data['skew_10'] = np.log(data['close']).diff().rolling(
    window=10, min_periods=10, center=False).skew()
data['skew_5'] =np.log(data['close']).diff().rolling(
    window=5, min_periods=5, center=False).skew()

# kurtosis
data['kurtosis_60'] = np.log(data['close']).diff().rolling(
    window=60, min_periods=60, center=False).kurt()
data['kurtosis_30'] = np.log(data['close']).diff().rolling(
    window=30, min_periods=30, center=False).kurt()
data['kurtosis_15'] = np.log(data['close']).diff().rolling(
    window=15, min_periods=15, center=False).kurt()
data['kurtosis_10'] = np.log(data['close']).diff().rolling(
    window=10, min_periods=10, center=False).kurt()
data['kurtosis_5'] =np.log(data['close']).diff().rolling(
    window=5, min_periods=5, center=False).kurt()

# microstructural features
data['roll_measure'] = micro.get_roll_measure(data['close'])
data['corwin_schultz_est'] = micro.get_corwin_schultz_estimator(
    data['high'], data['low'], 100)
data['bekker_parkinson_vol'] = micro.get_bekker_parkinson_vol(
    data['high'], data['low'], 100)
data['kyle_lambda'] = micro.get_bekker_parkinson_vol(
    data['close'], data['volume'])
data['amihud_lambda'] = micro.get_bar_based_amihud_lambda(
    data['close'], data['volume'])
data['hasbrouck_lambda'] = micro.get_bar_based_hasbrouck_lambda(
    data['close'], data['volume'])
tick_diff = data['close'].diff()
data['tick_rule'] = np.where(tick_diff != 0,
                             np.sign(tick_diff),
                             np.sign(tick_diff).shift(periods=-1))


### REMOVE NAN
data.isna().sum().sort_values(ascending=False).head(60)
if add_ta:
    data = data.loc[:, data.isna().sum() < (max(periods) + 100)]
cols_remove_na = range((np.where(data.columns == 'volume')[0].item() + 1), data.shape[1])
data.dropna(subset=data.columns[cols_remove_na], inplace=True)


### ADD VIX TO DATABASE
q = 'SELECT date, open AS open_vix, high AS high_vix, low AS low_vix, \
    close AS close_vix, volume AS volume_vix FROM VIX'
data_vix = tml.modeling.utils.query_to_db(q, 'odvjet12_market_data_usa')
data_vix.set_index(data_vix.date, inplace=True)
data_vix.drop(columns=['date'], inplace=True)
data_vix.sort_index(inplace=True)
# merge spy and vix with merge_asof which uses nearest back value for NA
data_vix = data_vix.sort_index()
data = pd.merge_asof(data, data_vix, left_index=True, right_index=True)

### VIX FEATURES
data['vix_high_low'] = data['high'] - data['low']
data['vix_close_open'] = data['close'] - data['open']


### 2) LABELING (COMPUTATIONALLY INTENSIVE)
if add_labels:
    # trend scanning
    def add_trend_scanning_label(data, look_forward, col_prefix=''):
        ts_1_day = tml.modeling.pipelines.trend_scanning_labels(
            data['close'], t_events=data.index, look_forward_window=observatins_per_day,
            min_sample_length=30, step=2
        )
        ts_1_day = ts_1_day.add_prefix(col_prefix)
        return pd.concat([data, ts_1_day], axis=1)

    
    observatins_per_day = int(pd.value_counts(data.index.normalize(), sort=False).mean())
    data = add_trend_scanning_label(data, observatins_per_day, 'day_1_')
    data = add_trend_scanning_label(data, observatins_per_day*2, 'day_2_')
    data = add_trend_scanning_label(data, observatins_per_day*3, 'day_3_')
    data = add_trend_scanning_label(data, observatins_per_day*5, 'day_5_')
    data = add_trend_scanning_label(data, observatins_per_day*10, 'day_10_')
    data = add_trend_scanning_label(data, observatins_per_day*20, 'day_20_')
    data = add_trend_scanning_label(data, observatins_per_day*30, 'day_30_')
    data = add_trend_scanning_label(data, observatins_per_day*60, 'day_60_')

# triple-barrier labeling


### 3) STRUCTURAL BRAKES

# convert data to hourly to make code faster and decrease random component
close_hourly = data['close'].resample('H').last().dropna()
close_hourly = np.log(close_hourly)

# Chow-Type Dickey-Fuller Test
chow = tml.modeling.structural_breaks.get_chow_type_stat(
    series=close_hourly, min_length=10)
breakdate = chow.loc[chow == chow.max()]
data['chow_segment'] = 0
data['chow_segment'][breakdate.index[0]:] = 1
data['chow_segment'].loc[breakdate.index[0]:] = 1
data['chow_segment'] = np.where(data.index < breakdate.index[0], 0, 1)
data['chow_segment'].value_counts()


### SAVE
# save localy
file_name = 'SPY_raw'
if add_ta:
    file_name = file_name + '_ta'
if add_labels:
    file_name = file_name + '_labels'
save_path_local = os.path.join(Path(save_path), file_name + '.h5')
if os.path.exists(save_path_local):
    os.remove(save_path_local)
with pd.HDFStore(save_path_local) as store:
    store.put(file_name, data)
# save to mfiles
if env_directory is not None:
    mfiles_client = tml.modeling.utils.set_mfiles_client(env_directory)
    tml.modeling.utils.destroy_mfiles_object(mfiles_client, [file_name + '.h5'])
    wd = os.getcwd()
    os.chdir(Path(save_path))
    mfiles_client.upload_file(file_name, object_type='Dokument')
    os.chdir(wd)


###  STATIONARITY
# save original ohlcv, I will need it later
ohlc = data[['open', 'high', 'low', 'close', 'chow_segment']]
ohlc.columns = ['open_orig', 'high_orig', 'low_orig', 'close_orig', 'chow_segment']


from statsmodels.tsa.stattools import adfuller
adfTest = data.apply(lambda x: adfuller(x, 
                                        maxlag=1,
                                        regression='c',
                                        autolag=None),
                        axis=0)
adfTestPval = [adf[1] for adf in adfTest]
adfTestPval = pd.Series(adfTestPval)
stationaryCols = data.loc[:, (adfTestPval > 0.1).to_list()].columns

# get minimum values of d for every column
seq = np.linspace(0, 1, 16)
min_d = data[stationaryCols].apply(lambda x: min_ffd_value(x.to_frame(), seq))






# get dmin for every column
stationaryCols, min_d = tml.modeling.stationarity.min_ffd_all_cols(data)

# save to github for later 
min_dmin_d_save_for_backtesting = pd.Series(0, index=data.columns)
min_dmin_d_save_for_backtesting.update(min_d)
min_dmin_d_save_for_backtesting.dropna(inplace=True)
min_dmin_d_save_for_backtesting.to_csv(
    'C:/Users/Mislav/Documents/GitHub/trademl/data/min_d_' + contract + '.csv', sep=';')

# convert unstationary to stationary
data = tml.modeling.stationarity.unstat_cols_to_stat(data, min_d, stationaryCols)  # tml.modeling.stationarity.unstat_cols_to_stat
data.dropna(inplace=True)

# merge orig ohlc to spyStat
data = data.merge(ohlc, how='left', left_index=True, right_index=True)





### SADF

# from typing import Union, Tuple

# def _lag_df(df: pd.DataFrame, lags: Union[int, list]) -> pd.DataFrame:
#     """
#     Advances in Financial Machine Learning, Snipet 17.3, page 259.
#     Apply Lags to DataFrame
#     :param df: (int or list) Either number of lags to use or array of specified lags
#     :param lags: (int or list) Lag(s) to use
#     :return: (pd.DataFrame) Dataframe with lags
#     """
#     df_lagged = pd.DataFrame()
#     if isinstance(lags, int):
#         lags = range(1, lags + 1)
#     else:
#         lags = [int(lag) for lag in lags]

#     for lag in lags:
#         temp_df = df.shift(lag).copy(deep=True)
#         temp_df.columns = [str(i) + '_' + str(lag) for i in temp_df.columns]
#         df_lagged = df_lagged.join(temp_df, how='outer')
#     return df_lagged

# def _get_y_x(series: pd.Series, model: str, lags: Union[int, list],
#              add_const: bool) -> Tuple[pd.DataFrame, pd.DataFrame]:
#     """
#     Advances in Financial Machine Learning, Snippet 17.2, page 258-259.
#     Preparing The Datasets
#     :param series: (pd.Series) Series to prepare for test statistics generation (for example log prices)
#     :param model: (str) Either 'linear', 'quadratic', 'sm_poly_1', 'sm_poly_2', 'sm_exp', 'sm_power'
#     :param lags: (int or list) Either number of lags to use or array of specified lags
#     :param add_const: (bool) Flag to add constant
#     :return: (pd.DataFrame, pd.DataFrame) Prepared y and X for SADF generation
#     """
#     series = pd.DataFrame(series)
#     series_diff = series.diff().dropna()
#     x = _lag_df(series_diff, lags).dropna()
#     x['y_lagged'] = series.shift(1).loc[x.index]  # add y_(t-1) column
#     y = series_diff.loc[x.index]

#     if add_const is True:
#         x['const'] = 1

#     if model == 'linear':
#         x['trend'] = np.arange(x.shape[0])  # Add t to the model (0, 1, 2, 3, 4, 5, .... t)
#         beta_column = 'y_lagged'  # Column which is used to estimate test beta statistics
#     elif model == 'quadratic':
#         x['trend'] = np.arange(x.shape[0]) # Add t to the model (0, 1, 2, 3, 4, 5, .... t)
#         x['quad_trend'] = np.arange(x.shape[0]) ** 2 # Add t^2 to the model (0, 1, 4, 9, ....)
#         beta_column = 'y_lagged'  # Column which is used to estimate test beta statistics
#     elif model == 'sm_poly_1':
#         y = series.loc[y.index]
#         x = pd.DataFrame(index=y.index)
#         x['const'] = 1
#         x['trend'] = np.arange(x.shape[0])
#         x['quad_trend'] = np.arange(x.shape[0]) ** 2
#         beta_column = 'quad_trend'
#     elif model == 'sm_poly_2':
#         y = np.log(series.loc[y.index])
#         x = pd.DataFrame(index=y.index)
#         x['const'] = 1
#         x['trend'] = np.arange(x.shape[0])
#         x['quad_trend'] = np.arange(x.shape[0]) ** 2
#         beta_column = 'quad_trend'
#     elif model == 'sm_exp':
#         y = np.log(series.loc[y.index])
#         x = pd.DataFrame(index=y.index)
#         x['const'] = 1
#         x['trend'] = np.arange(x.shape[0])
#         beta_column = 'trend'
#     elif model == 'sm_power':
#         y = np.log(series.loc[y.index])
#         x = pd.DataFrame(index=y.index)
#         x['const'] = 1
#         # TODO: Rewrite logic of this module to avoid division by zero
#         with np.errstate(divide='ignore'):
#             x['log_trend'] = np.log(np.arange(x.shape[0]))
#         beta_column = 'log_trend'
#     else:
#         raise ValueError('Unknown model')

#     # Move y_lagged column to the front for further extraction
#     columns = list(x.columns)
#     columns.insert(0, columns.pop(columns.index(beta_column)))
#     x = x[columns]
#     return x, y


# @njit
# def get_betas(X: np.array, y: np.array) -> Tuple[np.array, np.array]:
#     """
#     Advances in Financial Machine Learning, Snippet 17.4, page 259.
#     Fitting The ADF Specification (get beta estimate and estimate variance)
#     :param X: (pd.DataFrame) Features(factors)
#     :param y: (pd.DataFrame) Outcomes
#     :return: (np.array, np.array) Betas and variances of estimates
#     """

#     # Get regression coefficients estimates
#     xy_ = np.dot(X.T, y)
#     xx_ = np.dot(X.T, X)

#     #   check for singularity
#     det = np.linalg.det(xx_)

#     # get coefficient and std from linear regression
#     if det == 0:
#         b_mean = np.array([[np.nan]])
#         b_var = np.array([[np.nan, np.nan]])
#         return None
#     else:
#         xx_inv = np.linalg.inv(xx_)
#         b_mean = np.dot(xx_inv, xy_)
#         err = y - np.dot(X, b_mean)
#         b_var = np.dot(np.transpose(err), err) / (X.shape[0] - X.shape[1]) * xx_inv  # pylint: disable=E1136  # pylint/issues/3139
#         return b_mean, b_var
    

# @njit
# def _get_sadf_at_t(X: pd.DataFrame, y: pd.DataFrame, min_length: int, model: str, phi: float) -> float:
#     """
#     Advances in Financial Machine Learning, Snippet 17.2, page 258.
#     SADF's Inner Loop (get SADF value at t)
#     :param X: (pd.DataFrame) Lagged values, constants, trend coefficients
#     :param y: (pd.DataFrame) Y values (either y or y.diff())
#     :param min_length: (int) Minimum number of samples needed for estimation
#     :param model: (str) Either 'linear', 'quadratic', 'sm_poly_1', 'sm_poly_2', 'sm_exp', 'sm_power'
#     :param phi: (float) Coefficient to penalize large sample lengths when computing SMT, in [0, 1]
#     :return: (float) SADF statistics for y.index[-1]
#     """
#     start_points = prange(0, y.shape[0] - min_length + 1)
#     bsadf = -np.inf
#     for start in start_points:
#         y_, X_ = y[start:], X[start:]
#         b_mean_, b_std_ = get_betas(X_, y_)
#         # if b_mean_ is not None:  DOESNT WORK WITH NUMBA
#         b_mean_, b_std_ = b_mean_[0, 0], b_std_[0, 0] ** 0.5
#         # Rewrite logic of this module to avoid division by zero
#         if b_std_ != np.float64(0):
#             all_adf = b_mean_ / b_std_
#         if model[:2] == 'sm':
#             all_adf = np.abs(all_adf) / (y.shape[0]**phi)
#         if all_adf > bsadf:
#             bsadf = all_adf
#     return bsadf


# @njit
# def _sadf_outer_loop(X: np.array, y: np.array, min_length: int, model: str, phi: float,
#                      ) -> pd.Series:
#     """
#     This function gets SADF for t times from molecule
#     :param X: (pd.DataFrame) Features(factors)
#     :param y: (pd.DataFrame) Outcomes
#     :param min_length: (int) Minimum number of observations
#     :param model: (str) Either 'linear', 'quadratic', 'sm_poly_1', 'sm_poly_2', 'sm_exp', 'sm_power'
#     :param phi: (float) Coefficient to penalize large sample lengths when computing SMT, in [0, 1]
#     :param molecule: (list) Indices to get SADF
#     :return: (pd.Series) SADF statistics
#     """
#     sadf_series_val = []
#     for index in range(1, (y.shape[0]-min_length+1)):
#         X_subset = X[:min_length+index]
#         y_subset = y[:min_length+index]
#         value = _get_sadf_at_t(X_subset, y_subset, min_length, model, phi)
#         sadf_series_val.append(value)
#     return sadf_series_val



# def get_sadf(series: pd.Series, model: str, lags: Union[int, list], min_length: int, add_const: bool = False,
#              phi: float = 0, num_threads: int = 8, verbose: bool = True) -> pd.Series:
    
#     X, y = _get_y_x(series, model, lags, add_const)
#     molecule = y.index[min_length:y.shape[0]]
#     X_val = X.values
#     y_val = y.values
    
#     sadf_series =_sadf_outer_loop(X=X.values, y=y.values,
#                                   min_length=min_length, model=model, phi=phi)
#     sadf_series_val = np.array(sadf_series)
    
#     return sadf_series_val


# # convert data to hourly to make code faster and decrease random component
# close_daily = data['close_orig'].resample('D').last().dropna()
# close_daily = np.log(close_daily)


# series = close_daily.iloc[:2000].copy()
# model = 'linear'
# lags = 2
# min_length = 20
# add_const = False
# phi = 0


# MEASURE PERFORMANCE
# from timeit import default_timer as timer
# from datetime import timedelta

# # MLFINLAB PACKAGE
# start = timer()
# mlfinlab_results = ml.structural_breaks.get_sadf(
#     series, min_length=min_length, model=model, phi=phi, num_threads=1, lags=lags)
# end = timer()
# print(timedelta(seconds=end-start))
# print(mlfinlab_results.shape)
# print(mlfinlab_results.head(20))
# print(mlfinlab_results.tail(20))


# # MY FUNCTION
# start = timer()
# results = get_sadf(
#     close_daily, min_length=20, add_const='True', model='linear', phi=0.5, num_threads=1, lags=2)
# end = timer()
# print(timedelta(seconds=end-start))
# type(results)
# print(results.shape)
# print(results[:20])
# print(results[-25:])


### TREND SCANNING LABELING
# ts_look_forward_window = [60, 60*8, 60*8*5, 60*8*10, 60*8*15, 60*8*20]
# ts_min_sample_length = [5, 60, 60, 60, 60, 60]
# ts_step = [1, 5, 10, 15, 20, 25]




### SAVE TO DATABASE
# add to database
# data['date'] = data.index
# tml.modeling.utils.write_to_db(data.iloc[:50000], "odvjet12_ml_data_usa", 'SPY')
# write_to_db_update(data.iloc[50000:100000], "odvjet12_ml_data_usa", 'SPY')
# seq = np.append(np.arange(1561001, data.shape[0], 50000), (data.shape[0]+1))
# for index, i in enumerate(seq):
#     print(seq[index], seq[index+1])
#     write_to_db_update(data.iloc[seq[index]:seq[index+1]], "odvjet12_ml_data_usa", 'SPY')
    

### SAVE SPY WITH VIX

# save SPY
save_path = 'D:/market_data/usa/ohlcv_features/' + 'SPY' + '.h5'
with pd.HDFStore(save_path) as store:
    store.put('SPY', data)
