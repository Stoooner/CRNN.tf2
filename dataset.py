import os

import numpy as np
import tensorflow as tf


class OCRDataLoader():
    def __init__(self, 
                 annotation_paths, 
                 image_height, 
                 image_width, 
                 table_path, 
                 blank_index=0, 
                 batch_size=1, 
                 shuffle=False, 
                 repeat=1):
        
        imgpaths, labels = self.read_imagepaths_and_labels(annotation_paths)
        self.batch_size = batch_size
        self.image_width = image_width
        self.image_height = image_height
        self.size = len(imgpaths)

        file_init = tf.lookup.TextFileInitializer(table_path, 
                                                  tf.string, 
                                                  tf.lookup.TextFileIndex.WHOLE_LINE,
                                                  tf.int64,
                                                  tf.lookup.TextFileIndex.LINE_NUMBER)
        # Default value for blank label
        self.table = tf.lookup.StaticHashTable(initializer=file_init, default_value=blank_index)

        dataset = tf.data.Dataset.from_tensor_slices((imgpaths, labels))
        if shuffle:
            dataset = dataset.shuffle(buffer_size=self.size)
        dataset = dataset.map(self._decode_and_resize)
        # Ignore the errors e.g. decode error or invalid data.
        dataset = dataset.apply(tf.data.experimental.ignore_errors()) 
        # Pay attention to the location of the batch function.
        dataset = dataset.batch(batch_size)
        dataset = dataset.map(self._convert_label)
        dataset = dataset.repeat(repeat)

        self.dataset = dataset

    def read_imagepaths_and_labels(self, annotation_path):
        """Read txt file to get image paths and labels."""

        imgpaths = []
        labels = []
        for annpath in annotation_path.split(','):
            # If you use your own dataset, maybe you should change the parse code below.
            annotation_folder = os.path.dirname(annpath)
            with open(annpath) as f:
                content = np.array([line.strip().split() for line in f.readlines()])
            imgpaths_local = content[:, 0]
            # Parse MjSynth dataset. format: XX_label_XX.jpg XX
            # URL: https://www.robots.ox.ac.uk/~vgg/data/text/            
            labels_local = [line.split("_")[1] for line in imgpaths_local]

            # Parse example dataset. format: XX.jpg label
            # labels_local = content[:, 1]

            imgpaths_local = [os.path.join(annotation_folder, line) for line in imgpaths_local]
            imgpaths.extend(imgpaths_local)
            labels.extend(labels_local)

        return imgpaths, labels

    def _decode_and_resize(self, filename, label):
        image = tf.io.read_file(filename)
        image = tf.io.decode_jpeg(image, channels=1)
        image = tf.image.convert_image_dtype(image, tf.float32)
        image = tf.image.resize(image, [self.image_height, self.image_width])
        return image, label

    def _convert_label(self, image, label):
        chars = tf.strings.unicode_split(label, input_encoding="UTF-8")
        mapped_label = tf.ragged.map_flat_values(self.table.lookup, chars)
        sparse_label = mapped_label.to_sparse()
        sparse_label = tf.cast(sparse_label, tf.int32)
        return image, sparse_label

    def __call__(self):
        """Return tf.data.Dataset."""
        return self.dataset

    def __len__(self):
        return self.size


def map_to_chars(inputs, table, blank_index=0, merge_repeated=False):
    """Map to chars.
    
    Args:
        inputs: list of char ids.
        table: char map.
        blank_index: the index of blank.
        merge_repeated: True, Only if tf decoder is not used.

    Returns:
        lines: list of string.    
    """
    lines = []
    for line in inputs:
        text = ""
        previous_char = -1
        for char_index in line:
            if merge_repeated:
                if char_index == previous_char:
                    continue
            previous_char = char_index
            if char_index == blank_index:
                continue
            text += table[char_index]            
        lines.append(text)
    return lines

def map_and_count(decoded, Y, mapper, blank_index=0, merge_repeated=False):
    decoded = tf.sparse.to_dense(decoded[0], default_value=blank_index).numpy()
    Y = tf.sparse.to_dense(Y, default_value=blank_index).numpy()
    decoded = map_to_chars(decoded, mapper, blank_index=blank_index, merge_repeated=merge_repeated)
    Y = map_to_chars(Y, mapper, blank_index=blank_index, merge_repeated=merge_repeated)
    count = 0
    for y_pred, y in zip(decoded, Y):
        if y_pred == y:
            count += 1
    return count


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Process some integers.")
    parser.add_argument("-p", "--annotation_paths", type=str, help="The paths of annnotation file.")
    parser.add_argument("-t", "--table_path", type=str, help="The path of table file.")
    args = parser.parse_args()

    dataloader = OCRDataLoader(args.annotation_paths, 32, 100, table_path=args.table_path, shuffle=True, batch_size=2)
    print("Total have {} data".format(len(dataloader)))
    print("Element spec is: {}".format(dataloader().element_spec))
    for image, label in dataloader().take(1):
        label = tf.sparse.to_dense(label).numpy()
        print("The image's shape: {}\nlabel is \n{}".format(image.shape, label))