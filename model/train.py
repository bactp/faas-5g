"""
Train a simple CNN on CIFAR-10 and save the weights.
Run once during Docker build: python model/train.py
"""
import os
import numpy as np
import tensorflow as tf
from tensorflow.keras import layers, models

SAVE_PATH = os.environ.get("MODEL_PATH", "model/cifar10_model.h5")
EPOCHS = int(os.environ.get("EPOCHS", "20"))


def build_model():
    model = models.Sequential([
        layers.Input(shape=(32, 32, 3)),

        layers.Conv2D(32, (3, 3), padding="same", activation="relu"),
        layers.BatchNormalization(),
        layers.Conv2D(32, (3, 3), padding="same", activation="relu"),
        layers.MaxPooling2D((2, 2)),
        layers.Dropout(0.25),

        layers.Conv2D(64, (3, 3), padding="same", activation="relu"),
        layers.BatchNormalization(),
        layers.Conv2D(64, (3, 3), padding="same", activation="relu"),
        layers.MaxPooling2D((2, 2)),
        layers.Dropout(0.25),

        layers.Conv2D(128, (3, 3), padding="same", activation="relu"),
        layers.BatchNormalization(),
        layers.MaxPooling2D((2, 2)),
        layers.Dropout(0.25),

        layers.Flatten(),
        layers.Dense(256, activation="relu"),
        layers.Dropout(0.5),
        layers.Dense(10, activation="softmax"),
    ])
    return model


def main():
    print("Loading CIFAR-10 dataset...")
    (x_train, y_train), (x_test, y_test) = tf.keras.datasets.cifar10.load_data()

    x_train = x_train.astype("float32") / 255.0
    x_test  = x_test.astype("float32")  / 255.0

    # per-channel normalization
    mean = np.mean(x_train, axis=(0, 1, 2))
    std  = np.std(x_train,  axis=(0, 1, 2))
    x_train = (x_train - mean) / std
    x_test  = (x_test  - mean) / std

    # save normalization stats alongside model
    stats_path = os.path.splitext(SAVE_PATH)[0] + "_norm.npz"
    np.savez(stats_path, mean=mean, std=std)
    print(f"Normalization stats saved to {stats_path}")

    y_train = tf.keras.utils.to_categorical(y_train, 10)
    y_test  = tf.keras.utils.to_categorical(y_test,  10)

    model = build_model()
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=1e-3),
        loss="categorical_crossentropy",
        metrics=["accuracy"],
    )
    model.summary()

    callbacks = [
        tf.keras.callbacks.ReduceLROnPlateau(monitor="val_accuracy", patience=3, factor=0.5, verbose=1),
        tf.keras.callbacks.EarlyStopping(monitor="val_accuracy", patience=7, restore_best_weights=True),
    ]

    datagen = tf.keras.preprocessing.image.ImageDataGenerator(
        horizontal_flip=True,
        width_shift_range=0.1,
        height_shift_range=0.1,
    )

    print(f"Training for up to {EPOCHS} epochs...")
    model.fit(
        datagen.flow(x_train, y_train, batch_size=64),
        epochs=EPOCHS,
        validation_data=(x_test, y_test),
        callbacks=callbacks,
    )

    os.makedirs(os.path.dirname(SAVE_PATH) or ".", exist_ok=True)
    model.save(SAVE_PATH)
    loss, acc = model.evaluate(x_test, y_test, verbose=0)
    print(f"Test accuracy: {acc:.4f}  |  Model saved to {SAVE_PATH}")


if __name__ == "__main__":
    main()
