from pathlib import Path
import os
import numpy as np
import pandas as pd
from numba import njit
import matplotlib.pyplot as plt
import matplotlib
import sklearn
from sklearn import preprocessing
from sklearn.model_selection import train_test_split
import mlfinlab as ml
from mlfinlab.feature_importance import get_orthogonal_features
import trademl as tml
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers



### NON-MODEL HYPERPARAMETERS (for guildai)
# load and save data
input_data_path = 'D:/market_data/usa/ohlcv_features'
output_data_path = 'D:/algo_trading_files'
env_directory = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
# structural breaks
structural_break_regime = 'all'
# labeling
label_tuning = True
label = 'day_10'
labeling_technique = 'trend_scanning'
ts_look_forward_window = 240  # 60 * 8 * 10 (10 days)
ts_min_sample_length = 30
ts_step = 5
tb_triplebar_num_days = 10
tb_triplebar_pt_sl = [1, 1]
tb_triplebar_min_ret = 0.004
ts_look_forward_window = 1200  # 60 * 8 * 10 (10 days)
ts_min_sample_length = 30
ts_step = 5
tb_min_pct = 0.10
# filtering
tb_volatility_lookback = 500
tb_volatility_scaler = 1
# stationarity
stationarity_tecnique = 'orig'
# feature engineering
correlation_threshold = 0.95
pca = False
# scaling
scaling = None
# performace
num_threads = 1
# sequence generation
train_val_index_split = 0.9
time_step_length = 20


### IMPORT DATA
def import_data(data_path, remove_cols, contract='SPY'):
    # import data
    with pd.HDFStore(os.path.join(data_path, contract + '.h5')) as store:
        data = store.get(contract)
    data.sort_index(inplace=True)
    
    # remove variables
    remove_cols = [col for col in remove_cols if col in data.columns]
    data.drop(columns=remove_cols, inplace=True)
    
    return data


data = import_data(input_data_path, [], contract='SPY_raw')


### REGIME DEPENDENT ANALYSIS
if structural_break_regime == 'chow':
    if (data.loc[data['chow_segment'] == 1].shape[0] / 60 / 8) < 365:
        data = data.iloc[-(60*8*365):]
    else:
        data = data.loc[data['chow_segment'] == 1]
data = data.drop(columns=['chow_segment'])


### CHOOSE STATIONARY / UNSTATIONARY
if stationarity_tecnique == 'fracdiff':
    remove_cols = [col for col in data.columns if 'orig_' in col and col != 'orig_close']  
elif stationarity_tecnique == 'orig':
    remove_cols = [col for col in data.columns if 'fracdiff_' in col and col != 'orig_close']
data = data.drop(columns=remove_cols)


### LABELLING
if label_tuning:
    if labeling_technique == 'triple_barrier':
        # TRIPLE BARRIER LABELING
        triple_barrier_pipe= tml.modeling.pipelines.TripleBarierLabeling(
            close_name='orig_close' if 'orig_close' in data.columns else 'close',
            volatility_lookback=tb_volatility_lookback,
            volatility_scaler=tb_volatility_scaler,
            triplebar_num_days=tb_triplebar_num_days,
            triplebar_pt_sl=tb_triplebar_pt_sl,
            triplebar_min_ret=tb_triplebar_min_ret,
            num_threads=num_threads,
            tb_min_pct=tb_min_pct
        )   
        tb_fit = triple_barrier_pipe.fit(data)
        labeling_info = tb_fit.triple_barrier_info
        X = tb_fit.transform(data)
    elif labeling_technique == 'trend_scanning':
        trend_scanning_pipe = tml.modeling.pipelines.TrendScanning(
            close_name='orig_close' if 'orig_close' in data.columns else 'close',
            volatility_lookback=tb_volatility_lookback,
            volatility_scaler=tb_volatility_scaler,
            ts_look_forward_window=ts_look_forward_window,
            ts_min_sample_length=ts_min_sample_length,
            ts_step=ts_step
            )
        labeling_info = trend_scanning_pipe.fit(data)
        X = trend_scanning_pipe.transform(data)
    elif labeling_technique == 'fixed_horizon':
        X = data.copy()
        labeling_info = ml.labeling.fixed_time_horizon(data['orig_close'], threshold=0.005, resample_by='B').dropna().to_frame()
        labeling_info = labeling_info.rename(columns={'orig_close': 'bin'})
        print(labeling_info.iloc[:, 0].value_counts())
        X = X.iloc[:-1, :]
else:
    X_cols = [col for col in data.columns if 'day_' not in col]
    X = data[X_cols]
    y_cols = [col for col in data.columns if label in col]
    labeling_info = data[y_cols]


### FILTERING
if not label_tuning:
    daily_vol = ml.util.get_daily_vol(data['orig_close' if 'orig_close' in data.columns else 'close'], lookback=50)
    cusum_events = ml.filters.cusum_filter(data['orig_close' if 'orig_close' in data.columns else 'close'], threshold=daily_vol.mean()*1)
    ### ZAVRSITI DO KRAJA ####
else:
    daily_vol = ml.util.get_daily_vol(data['orig_close' if 'orig_close' in data.columns else 'close'], lookback=50)
    cusum_events = ml.filters.cusum_filter(data['orig_close' if 'orig_close' in data.columns else 'close'], threshold=daily_vol.mean()*1)


### REMOVE NA
remove_na_rows = labeling_info.isna().any(axis=1)
X = X.loc[~remove_na_rows]
labeling_info = labeling_info.loc[~remove_na_rows]
labeling_info.iloc[:, -1] = np.where(labeling_info.iloc[:, -1] == -1, 0, labeling_info.iloc[:, -1])
# labeling_info.iloc[:, -1] = labeling_info.iloc[:, -1].astype(pd.Int64Dtype())


### REMOVE CORRELATED ASSETS
X = tml.modeling.preprocessing.remove_correlated_columns(
    data=X,
    columns_ignore=[],
    threshold=correlation_threshold)


### TRAIN TEST SPLIT
X_train, X_test, y_train, y_test = train_test_split(
    X, labeling_info.loc[:, labeling_info.columns.str.contains('bin')],
    test_size=0.10, shuffle=False, stratify=None)


### SCALING
if scaling == 'expanding':
    stdize_input = lambda x: (x - x.expanding(50).mean()) / x.expanding(50).std()
    X_train = X_train.apply(stdize_input)
    X_test = X_test.apply(stdize_input)
    y_train = y_train.loc[~X_train.isna().any(axis=1)]
    X_train = X_train.dropna()
    y_test = y_test.loc[~X_test.isna().any(axis=1)]
    X_test = X_test.dropna()
    



# test for shapes
# print('X and y shape train: ', X_train_seq.shape, y_train_seq.shape)
# print('X and y shape validate: ', X_val_seq.shape, y_val_seq.shape)
# print('X and y shape test: ', X_test_seq.shape, y_test_seq.shape)



### TEST MODEL
# model = keras.Sequential()
# model.add(layers.LSTM(32,
#                       return_sequences=True,
#                       input_shape=[None, X_train.shape[1]]))
# model.add(layers.LSTM(32, dropout=0.2))
# model.add(layers.Dense(1, activation='sigmoid'))
# model.compile(loss='binary_crossentropy',
#                 optimizer=keras.optimizers.Adam(),
#                 metrics=['accuracy',
#                         keras.metrics.AUC(),
#                         keras.metrics.Precision(),
#                         keras.metrics.Recall()]
#                 )
# history = model.fit(X_train_seq, y_train_seq, batch_size=128, epochs = 5, validation_data = (X_val_seq, y_val_seq))
