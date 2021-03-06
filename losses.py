import math

import numpy as np

import tensorflow as tf
import tensorflow_probability as tfp

import datasets
import utils

def get_lr(lr, dataset, batch_size, schedule_mode="constant", step_factor=1):
    steps_per_epoch = int(datasets.dataset_size[dataset][0] / batch_size)

    if schedule_mode == "constant":
        return lr
    elif schedule_mode == "keras_resnet20_cifar10":
        # ref: https://keras.io/examples/cifar10_resnet/
        values = [1e-3, 1e-4, 1e-5, 1e-6, 0.5e-6]
        steps = [80, 120, 160, 180]
        return tf.keras.optimizers.schedules.PiecewiseConstantDecay(
            (np.array(steps) * steps_per_epoch / step_factor).tolist(),
            values
        )
    elif schedule_mode == "pytorch_resnet20_cifar10":
        # ref: https://github.com/akamaster/pytorch_resnet_cifar10/blob/master/trainer.py#L120
        values = [1e-1, 1e-2, 1e-3]
        return tf.keras.optimizers.schedules.PiecewiseConstantDecay(
            (np.array([100, 150]) * steps_per_epoch / step_factor).tolist(),
            values
        )
    elif schedule_mode == "alemi_vib_mnist":
        # ref: https://github.com/alexalemi/vib_demo/blob/master/MNISTVIB.ipynb
        return tf.keras.optimizers.schedules.ExponentialDecay(
            lr,
            decay_steps=2*steps_per_epoch,
            decay_rate=0.97,
            staircase=True
        )
    else:
        raise ValueError(f"no lr_schedule: {schedule_mode}")

def get_optimizer(strategy, lr, lr_schedule, dataset, batch_size):
    strategy_name = strategy.split("/")[0]
    if strategy_name == "oneshot":
        print("using oneshot strategy")

        lr = get_lr(lr, dataset, batch_size, schedule_mode=lr_schedule)

        return [
            # this parameter from  https://github.com/alexalemi/vib_demo/blob/master/MNISTVIB.ipynb
            tf.keras.optimizers.Adam(lr, 0.5)
        ], strategy, {}
    elif strategy == "algo1":
        slugs = strategy.split("/")
        print(f"using {slugs[0]} strategy with {slugs[1]}")

        opt_params = utils.parse_arch(slugs[1])

        if lr_schedule != "constant":
            raise ValueError(f"{strategy_name} is not yet supported lr_schedule")

        lr = get_lr(lr, dataset, batch_size, schedule_mode=lr_schedule)

        # one for encoder and decoder
        return (
            tf.keras.optimizers.Adam(lr, 0.5),
            tf.keras.optimizers.Adam(lr, 0.5)
        ), slugs[0], opt_params

    elif strategy_name == "algo2":
        slugs = strategy.split("/")
        print(f"using {slugs[0]} strategy with {slugs[1]}")

        opt_params = utils.parse_arch(slugs[1])

        # one for encoder and decoder
        return (
            tf.keras.optimizers.Adam(
                get_lr(lr, dataset, batch_size, schedule_mode=lr_schedule),
                0.5
            ),
            tf.keras.optimizers.Adam(
                get_lr(lr, dataset, batch_size, schedule_mode=lr_schedule, step_factor=opt_params["k"]),
                0.5
            ),
        ), slugs[0], opt_params

@tf.function
def mean_softmax_from_logits(logits):
    # logit's shape: (M, batch_size, 10)

    # shape: (M, batch_size, 10)
    sm = tf.nn.softmax(logits - tf.reduce_max(logits, 2, keepdims=True))

    # shape: (batch_size, 10)
    return tf.reduce_mean(sm, 0)

@tf.function
def compute_vib_class_loss(logits, y):
    # shape: (batch_size, 10)
    one_hot = tf.one_hot(y, depth=10, dtype=tf.float64)

    class_loss_float64 = tf.reduce_mean( # average across all samples in batch
        - tf.reduce_sum(
            tf.multiply(tf.reduce_mean(tf.math.log_softmax(logits), 0), one_hot),
            1 # sum over all classes
        )
    ) / math.log(2.)

    return class_loss_float64

@tf.function
def compute_vdb_class_loss(logits, y):
    # shape: (batch_size, 10)
    one_hot = tf.one_hot(y, depth=10, dtype=tf.float64)

    mean_sm = mean_softmax_from_logits(logits)

    class_loss_float64 = tf.reduce_mean( # average across all samples in batch
        - tf.reduce_sum(
            # tf.multiply(tf.reduce_mean(tf.nn.log_softmax(logits), 0), one_hot),
            tf.multiply(tf.math.log(mean_sm), one_hot),
            1 # sum over all classes
        )
    ) / math.log(2.)

    return class_loss_float64

@tf.function
def compute_info_loss_diag_cov(q_zgx, prior):
    return tf.cast(
        tf.reduce_sum(
            tf.reduce_mean(
                tfp.distributions.kl_divergence(q_zgx, prior),
                0
            )
        ) / math.log(2.),
        dtype=tf.float64
    )

@tf.function
def compute_info_loss_full_cov(q_zgx, prior):
    return tf.cast(tf.reduce_mean(
        tfp.distributions.kl_divergence(q_zgx, prior)
    ) / math.log(2.),
        dtype=tf.float64
    )


@tf.function
def compute_loss(model, x, y, M, training=False):
    # shape: (batch_size, 10)
    (mu, cov_entries), logits = model(x, L=M, training=training)

    q_zgx = model._build_z_dist(mu, cov_entries)

    class_loss = model.class_loss(logits, y)
    info_loss = model.info_loss(q_zgx, model.prior)

    IZY_bound = math.log(10, 2) - class_loss
    IZX_bound = info_loss

    return class_loss + model.beta*info_loss, IZY_bound, IZX_bound

@tf.function
def compute_apply_oneshot_gradients(model, batch, optimizers, epoch, opt_params, M, training=False):
    optimizer = optimizers[0]

    with tf.GradientTape() as tape:
        x, y = batch
        metrics = compute_loss(model, x, y, M, training=training)
        loss = metrics[0]

    gradients = tape.gradient(loss, model.trainable_variables)

    optimizer.apply_gradients(zip(gradients, model.trainable_variables))

    return metrics

@tf.function
def compute_apply_algo1_gradients(model, batch, optimizers, epoch, opt_params, M, training=False):
    enc_opt, dec_opt = optimizers

    with tf.GradientTape() as enc_tape, tf.GradientTape() as dec_tape:
        x, y = batch
        metrics = compute_loss(model, x, y, M, training=training)
        loss = metrics[0]

    if tf.equal(epoch % opt_params["d"], 0):
        dec_opt.apply_gradients(
            zip(
                dec_tape.gradient(
                    loss,
                    model.decoder.trainable_variables
                ),
                model.decoder.trainable_variables
            )
        )

    if tf.equal(epoch % opt_params["e"], 0):
        enc_opt.apply_gradients(
            zip(
                enc_tape.gradient(
                    loss,
                    model.encoder.trainable_variables
                ),
                model.encoder.trainable_variables
            )
        )

    return metrics

def compute_apply_gradients_variables(model, variables, batch, optimizer, M, training=False):
    with tf.GradientTape() as tape:
        x, y = batch
        metrics = compute_loss(model, x, y, M, training=training)
        loss = metrics[0]

    optimizer.apply_gradients(
        zip(tape.gradient(loss, variables), variables)
    )

    return metrics

@tf.function
def compute_apply_gradients_algo2_enc(model, variables, batch, optimizer, M, training=False):
    return compute_apply_gradients_variables(model, variables, batch, optimizer, M, training=training)

@tf.function
def compute_apply_gradients_algo2_dec(model, variables, batch, optimizer, M, training=False):
    return compute_apply_gradients_variables(model, variables, batch, optimizer, M, training=training)

def compute_vdb_class_loss_tf1(logits, y):
    # this is only for testing purposes.
    # logits's size = (M, Batch, 10)
    # y's size = (10,)

    one_hot_labels = tf.one_hot(y, depth=10, dtype=tf.float64)

    return tf.reduce_mean(
        -tf.reduce_sum(
            one_hot_labels * tf.math.log(
                tf.reduce_mean(tf.nn.softmax(logits), 0)
            ),
        1)
    ) / math.log(2)