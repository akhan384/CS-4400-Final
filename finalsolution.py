import pandas as pd
import numpy as np
from os.path import join

# 1. read data

ltable = pd.read_csv(join('data', "/content/drive/MyDrive/4400Final/ltable.csv"))
rtable = pd.read_csv(join('data', "/content/drive/MyDrive/4400Final/rtable.csv"))
train = pd.read_csv(join('data', "/content/drive/MyDrive/4400Final/train.csv"))


# 2. blocking
def pairs2LR(ltable, rtable, candset):
    ltable.index = ltable.id
    rtable.index = rtable.id
    pairs = np.array(candset)
    tpls_l = ltable.loc[pairs[:, 0], :]
    tpls_r = rtable.loc[pairs[:, 1], :]
    tpls_l.columns = [col + "_l" for col in tpls_l.columns]
    tpls_r.columns = [col + "_r" for col in tpls_r.columns]
    tpls_l.reset_index(inplace=True, drop=True)
    tpls_r.reset_index(inplace=True, drop=True)
    LR = pd.concat([tpls_l, tpls_r], axis=1)
    return LR


def block_by_brand(ltable, rtable):
    # ensure brand is str
    ltable['brand'] = ltable['brand'].astype(str)
    rtable['brand'] = rtable['brand'].astype(str)

    # get all brands
    brands_l = set(ltable["brand"].values)
    brands_r = set(rtable["brand"].values)
    brands = brands_l.union(brands_r)

    # map each brand to left ids and right ids
    brand2ids_l = {b.lower(): [] for b in brands}
    brand2ids_r = {b.lower(): [] for b in brands}
    for i, x in ltable.iterrows():
        brand2ids_l[x["brand"].lower()].append(x["id"])
    for i, x in rtable.iterrows():
        brand2ids_r[x["brand"].lower()].append(x["id"])

    # put id pairs that share the same brand in candidate set
    candset = []
    for brd in brands:
        l_ids = brand2ids_l[brd]
        r_ids = brand2ids_r[brd]
        for i in range(len(l_ids)):
            for j in range(len(r_ids)):
                candset.append([l_ids[i], r_ids[j]])
    return candset

# blocking to reduce the number of pairs to be compared
candset = block_by_brand(ltable, rtable)
print("number of pairs originally", ltable.shape[0] * rtable.shape[0])
print("number of pairs after blocking",len(candset))
candset_df = pairs2LR(ltable, rtable, candset)



# 3. Feature engineering
import Levenshtein as lev

def jaccard_similarity(row, attr):
    x = set(row[attr + "_l"].lower().split())
    y = set(row[attr + "_r"].lower().split())
    return len(x.intersection(y)) / max(len(x), len(y))


def levenshtein_distance(row, attr):
    x = row[attr + "_l"].lower()
    y = row[attr + "_r"].lower()
    return lev.distance(x, y)

def feature_engineering(LR):
    LR = LR.astype(str)
    attrs = ["title", "category", "brand", "modelno", "price"]
    features = []
    for attr in attrs:
        j_sim = LR.apply(jaccard_similarity, attr=attr, axis=1)
        l_dist = LR.apply(levenshtein_distance, attr=attr, axis=1)
        features.append(j_sim)
        features.append(l_dist)
    features = np.array(features).T
    return features
candset_features = feature_engineering(candset_df)

# also perform feature engineering to the training set
training_pairs = list(map(tuple, train[["ltable_id", "rtable_id"]].values))
training_df = pairs2LR(ltable, rtable, training_pairs)
training_features = feature_engineering(training_df)
training_label = train.label.values

# 4. Neural Network
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers

model = keras.Sequential()
model.add(layers.Dense(12, input_dim=10, activation="relu"))
model.add(layers.Dense(8, activation='relu'))
model.add(layers.Dense(1, activation='sigmoid'))
model.compile(optimizer='rmsprop',
              loss='binary_crossentropy',
              metrics=['accuracy'])


# 5. Train the model, iterating on the data in batches of 10 samples

model.fit(training_features, training_label, epochs=150, batch_size=10)


# 6. output

#Converting predictions to label
y_pred = model.predict_classes(candset_features)

matching_pairs = candset_df.loc[y_pred == 1, ["id_l", "id_r"]]
matching_pairs = list(map(tuple, matching_pairs.values))

matching_pairs_in_training = training_df.loc[training_label == 1, ["id_l", "id_r"]]
matching_pairs_in_training = set(list(map(tuple, matching_pairs_in_training.values)))

pred_pairs = [pair for pair in matching_pairs if
              pair not in matching_pairs_in_training]  # remove the matching pairs already in training
pred_pairs = np.array(pred_pairs)
pred_df = pd.DataFrame(pred_pairs, columns=["ltable_id", "rtable_id"])
pred_df.to_csv("output.csv", index=False)
