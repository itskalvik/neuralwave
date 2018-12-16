from tensorflow import keras
from keras.models import Model
from keras.layers import Input, Add, PReLU, Conv2DTranspose, Concatenate, MaxPooling2D, UpSampling2D, Dropout, BatchNormalization, Conv2D, Conv1D,Activation, ZeroPadding2D
from keras.callbacks import Callback
from keras.initializers import TruncatedNormal
from keras.engine.topology import Layer
from keras import backend as K
from keras.layers import Lambda
from keras import backend as K

eps = 1.1e-5

class L0Loss:
    def __init__(self):
        self.gamma = K.variable(2.)

    def __call__(self):
        def calc_loss(y_true, y_pred):
            loss = K.pow(K.abs(y_true - y_pred) + 1e-8, self.gamma)
            return loss
        return calc_loss

class UpdateAnnealingParameter(Callback):
    def __init__(self, gamma, nb_epochs, verbose=0):
        super(UpdateAnnealingParameter, self).__init__()
        self.gamma = gamma
        self.nb_epochs = nb_epochs
        self.verbose = verbose

    def on_epoch_begin(self, epoch, logs=None):
        new_gamma = 2.0 * (self.nb_epochs - epoch) / self.nb_epochs
        K.set_value(self.gamma, new_gamma)

        if self.verbose > 0:
            print('\nEpoch %05d: UpdateAnnealingParameter reducing gamma to %s.' % (epoch + 1, new_gamma))

def tf_log10(x):
    numerator = tf.log(x)
    denominator = tf.log(tf.constant(10, dtype=numerator.dtype))
    return numerator / denominator

def PSNR(y_true, y_pred):
    max_pixel = 1.0
    y_pred = K.clip(y_pred, 0.0, 1.0)
    return 10.0 * tf_log10((max_pixel ** 2) / (K.mean(K.square(y_pred - y_true))))

'''
UNet: code from https://github.com/pietz/unet-keras
U-Net: Convolutional Networks for Biomedical Image Segmentation
(https://arxiv.org/abs/1505.04597)
---
img_shape: (height, width, channels)
out_ch: number of output channels
start_ch: number of channels of the first conv
depth: zero indexed depth of the U-structure
inc_rate: rate at which the conv channels will increase
activation: activation function after convolutions
dropout: amount of dropout in the contracting part
batchnorm: adds Batch Normalization if true
maxpool: use strided conv instead of maxpooling if false
upconv: use transposed conv instead of upsamping + conv if false
residual: add residual connections around each conv block if true
'''
def identity_block_1D(input_tensor, filters, activation_func):
    filters1, filters2 = filters
    bn_axis = -1

    x = BatchNormalization(axis=bn_axis)(input_tensor)
    x = Activation(activation_func)(x)
    x = Conv1D(filters1, (1, 1))(x)

    x = BatchNormalization(axis=bn_axis)(x)
    x = Activation(activation_func)(x)
    x = Conv1D(filters2, (3, 3), padding='same')(x)

    x = Concatenate([x, input_tensor])
    return x

def conv_block_1D(input_tensor, filters, activation_func, strides=(2, 2)):
    filters1, filters2 = filters
    bn_axis = -1

    x = BatchNormalization(axis=bn_axis)(input_tensor)
    x = Activation(activation_func)(x)
    x = Conv1D(filters1, (1, 1), strides=strides)(x)

    x = BatchNormalization(axis=bn_axis)(x)
    x = Activation(activation_func)(x)
    x = Conv1D(filters2, (3, 3), padding='same')(x)

    shortcut = BatchNormalization(axis=bn_axis)(input_tensor)
    shortcut = Activation(activation_func)(shortcut)
    shortcut = Conv2D(filters2, (1, 1), strides=strides)(shortcut)

    x = Concatenate([x, shortcut])
    return x

def identity_block(input_tensor, filters, activation_func):
    filters1, filters2 = filters
    bn_axis = -1

    x = BatchNormalization(axis=bn_axis)(input_tensor)
    x = Activation(activation_func)(x)
    x = Conv2D(filters1, (1, 1))(x)

    x = BatchNormalization(axis=bn_axis)(x)
    x = Activation(activation_func)(x)
    x = Conv2D(filters2, (3, 3), padding='same')(x)

    x = Concatenate()([x, input_tensor])
    return x

def conv_block(input_tensor, filters, activation_func, strides=(2, 2)):
    filters1, filters2 = filters
    bn_axis = -1

    x = BatchNormalization(axis=bn_axis)(input_tensor)
    x = Activation(activation_func)(x)
    x = Conv2D(filters1, (1, 1), strides=strides)(x)

    x = BatchNormalization(axis=bn_axis)(x)
    x = Activation(activation_func)(x)
    x = Conv2D(filters2, (3, 3), padding='same')(x)

    shortcut = BatchNormalization(axis=bn_axis)(input_tensor)
    shortcut = Activation(activation_func)(shortcut)
    shortcut = Conv2D(filters2, (1, 1), strides=strides)(shortcut)

    x = Concatenate()([x, shortcut])
    return x

def level_block(m, filters, activation_func, depth, inc_rate):
    if depth > 0:
        n = identity_block(m, filters, activation_func)
        m = MaxPooling2D()(n)
        m = level_block(m, [inc_rate*x for x in filters], activation_func, depth - 1, inc_rate)
        m = UpSampling2D()(m)
        m = Conv2D(filters[-1], 2, activation=activation_func, padding='same')(m)
        n = Concatenate()([n, m])
        m = identity_block(n, filters, activation_func)
    else:
        m = identity_block(m, filters, activation_func)

    return m

def get_unet_model(input_channel_num, output_channel_num, filters=[4, 4, 8], activation_func='relu', depth=3, inc_rate=2):
    i = Input(shape=(None, None, input_channel_num))
    o = level_block(i, filters, activation_func, depth, inc_rate)
    o = Conv2D(output_channel_num, 1, activation='sigmoid')(o)
    model = Model(inputs=i, outputs=o)

    return model

if __name__ == '__main__':
    pass