import os
import sys
import math
import pickle
import numpy as np
from mpi4py import MPI
from sklearn.model_selection import train_test_split

def smooth(x,window_len):
    s=np.r_[x[window_len-1:0:-1],x,x[-2:-window_len-1:-1]]
    w=np.hanning(window_len)
    y=np.convolve(w/w.sum(),s,mode='valid')
    return y[(window_len//2):-(window_len//2)]

def read_samples(dataset_path, endswith=".csv"):
    datapaths, labels = list(), list()
    label = 0
    classes = sorted(os.listdir(dataset_path))
    # List each sub-directory (the classes)
    for c in classes:
        c_dir = os.path.join(dataset_path, c)
        walk = os.listdir(c_dir)
        # Add each image to the training set
        for sample in walk:
            # Only keeps csv samples
            if sample.endswith(endswith):
                datapaths.append(os.path.join(c_dir, sample))
                labels.append(label)
        label += 1
    return np.array(datapaths), np.array(labels), classes

def read_array(data_path):
    return np.loadtxt(open(data_path, "rb"), delimiter=",", dtype=np.float32)

def process_sample(data_path, dest_path, min_, max_, means):
    data = read_array(data_path)
    for i in range(cols):
        data[:, i] = smooth(data[:, i], filter)
    data -= means
    for i in range(cols):
        data[:, i] = (data[:, i] - min_[i])/(max_[i] - min_[i])

    if (data.shape != (rows, cols)):
        print(data.shape, data_path)
        sys.stdout.flush()
        return

    path, file = os.path.split(data_path)
    _, class_name = os.path.split(path)

    np.savetxt((os.path.join(os.path.join(dest_path, class_name), file)), data.astype(np.float32), delimiter=",")

#******************************************************************************#

src_path = "/scratch/kjakkala/neuralwave/data/preprocess_level2_new"
dest_path = "/scratch/kjakkala/neuralwave/data/preprocess_level3_new"
scalers_path = "/scratch/kjakkala/neuralwave/data/scalers_new.pkl"
rows = 8000
cols = 540
filter = 91

comm = MPI.COMM_WORLD
size = comm.Get_size()
rank = comm.Get_rank()

X, y, classes = read_samples(src_path)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.15, random_state=42)

num_sl = int(math.floor(len(X_train)/size))
train_sl = [None for _ in range(num_sl)]
train_array = None
last_sl = None

data_c_len = int(math.floor(len(X))/size)
data_c = [None for _ in range(data_c_len)]
data_c_last = None

if (rank == 0):
    print("train size:", len(X_train), "test size:", len(X_test))
    sys.stdout.flush()

    train_sl = [X_train[i:i+size] for i in range(0, len(X_train), size)]
    train_array = np.empty((size, rows, cols), dtype=np.float32)

    if (len(train_sl[-1]) != size):
        last_sl = train_sl[-1]
        del train_sl[-1]

    means = []
    mins = []
    maxs = []

    print("Started calculating means")
    sys.stdout.flush()

################################################################################
#mean
for index in range(num_sl):
    addr = comm.scatter(train_sl[index], root=0)
    comm.Gatherv(np.expand_dims(read_array(addr), axis=0), train_array, root=0)

    if (rank == 0):
        for i in range(size):
            for j in range(cols):
                train_array[i, :, j] = smooth(train_array[i, :, j], filter)
        means.extend(np.mean(train_array, axis=1))
        sys.stdout.write("\r{}/{}".format(index+1, num_sl))
        sys.stdout.flush()

if (rank == 0):
    if isinstance(last_sl, (list,)):
        train_array = np.array([read_array(addr) for addr in last_sl])
        for i in range(train_array.shape[0]):
            for j in range(cols):
                train_array[i, :, j] = smooth(train_array[i, :, j], filter)
        means.extend(np.mean(train_array, axis=1))
    means = np.mean(means, axis=0)

    print("\nStarted calculating min/max")
    sys.stdout.flush()
################################################################################
#min/max
for index in range(num_sl):
    addr = comm.scatter(train_sl[index], root=0)
    comm.Gatherv(np.expand_dims(read_array(addr), axis=0), train_array, root=0)

    if (rank == 0):
        for i in range(size):
            for j in range(cols):
                train_array[i, :, j] = smooth(train_array[i, :, j], filter)
        train_array -= means
        mins.extend(np.min(train_array, axis=1))
        maxs.extend(np.max(train_array, axis=1))
        sys.stdout.write("\r{}/{}".format(index+1, num_sl))
        sys.stdout.flush()

if (rank == 0):
    if isinstance(last_sl, (list,)):
        train_array = np.array([read_array(addr) for addr in last_sl])
        for i in range(train_array.shape[0]):
            for j in range(cols):
                train_array[i, :, j] = smooth(train_array[i, :, j], filter)
        train_array -= means
        mins.extend(np.min(train_array, axis=1))
        maxs.extend(np.max(train_array, axis=1))

    mins = np.min(np.min(train_array, axis=0), axis=0)
    maxs = np.max(np.max(train_array, axis=0), axis=0)
################################################################################

    dict = {"means":means, "min":mins, "max":maxs}
    fileObject = open(scalers_path,'wb')
    pickle.dump(dict, fileObject)
    fileObject.close()

    if not os.path.exists(os.path.join(dest_path, "train")):
        os.makedirs(os.path.join(dest_path, "train"))
        for i in classes:
            os.makedirs(os.path.join(os.path.join(dest_path, "train"), i))

    if not os.path.exists(os.path.join(dest_path, "test")):
        os.makedirs(os.path.join(dest_path, "test"))
        for i in classes:
            os.makedirs(os.path.join(os.path.join(dest_path, "test"), i))

    data_tmp = [[X_train[i], os.path.join(dest_path, "train"), mins, maxs, means] for i in range(len(X_train))]
    data_tmp.extend([X_test[i], os.path.join(dest_path, "test"), mins, maxs, means] for i in range(len(X_test)))
    data_c = [data_tmp[i:i+size] for i in range(0, len(data_tmp), size)]

    if (len(data_c[-1]) < size):
        data_c_last = data_c[-1]
        del data_c[-1]

    print("\nStarted writing csv files")
    sys.stdout.flush()

for index in range(data_c_len):
    data_tmp = comm.scatter(data_c[index], root=0)
    process_sample(data_tmp[0], data_tmp[1], data_tmp[2], data_tmp[3], data_tmp[4])

    if (rank == 0):
        sys.stdout.write("\r{}/{}".format(index+1, data_c_len))
        sys.stdout.flush()

if (rank == 0):
    if isinstance(data_c_last, (list,)):
        for data_tmp in data_c_last:
            process_sample(data_tmp[0], data_tmp[1], data_tmp[2], data_tmp[3], data_tmp[4])

print("\nFinished !!")
sys.stdout.flush()
