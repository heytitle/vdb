# Variation Deficiency Bottleneck

```
(Unofficial) implemenation of Banerjee and Montúfar (2020), Variational Deficiency Bottleneck, IJCNN 2020
```

## Dependencies
Please run `pip install -r requirements.txt` for installing all depedencies.

## Project Structures
### Training CLI
`train.py` provides the training CLI. Below is its usage:
```
Usage:
train.py  [--epoch=<epoch> --beta=<beta> -M=<M> --lr=<lr>] --strategy=<strategy> --dataset=<dataset> <model>

Options:
  -h --help                   Show this screen.
  --dataset=<dataset>         One from {mnist, fashion_mnist, cifar10} [default: mnist]
  --beta=<beta>               Value of β [default: 0.001]
  -M=<M>                      Value of M [default: 1]
  --lr=<lr>                   Learning rate [default: 0.001]
  --epoch=<epoch>             Number of epochs [default: 10]
  --strategy=<strategy>       Optimizaton strategy. See README.md for more details.
  --output-dir=<output-dir>   [default: ./artifacts]
  --class-loss=<class-loss>   Class loss {vdb, vib} [default: vdb]
  --cov-type=<cov-type>       Type of covariance {diag, full} [default: diag]
  --batch-size=<batch-size>   Batch size [default: 100]
```

#### Example

```
python train.py --epoch 5 \
 --strategy="algo1/d:10|e:1" \
 --dataset cifar10 \
 -M 1 \
 --class-los vdb \
 --cov-type full \
 --batch-size 256 \
 --lr 0.0001 \
 "mlp/e1:24|e2:24|z:20" 
```

### Running Unit tests
```
pytest tests.py
```

**Note:** Currently, we just have a test for verifying results of the class loss from TF1 and TF2 implementations.


### Core Modules
- `nets/*` contains the details of our models, i.e. how its architecture and computation look like. These architectures include
  - `base`: abstract architecture.
  - `mlp`: 2-layer MLP, based on what described in the VIB paper.
    - Usage: `mlp/e1:24|e2:24|z:20` (20 latent dimensions)
  - `resnet20`:
    - Usage: `resnet20/z:2` (2 latent dimensions)
- `losses.py` contains the IB loss function and the implementations of optimization strategies:
  - oneshot
  - sequential
- `datasets.py` provides a function to get any dataset from Keras based on `name`. Datasets we have include MNIST, FashionMNIST, and CIFAR10.

### Utility Modules
- `plot_helper.py`
- `tfutils.py`
- `utils.py`

### Analysis Scripts
Analyssis scripts locate in `./scripts/*-analysis.py`. These scripts load trained models and perform analysis accordingly. Results of the analysises are saved to files, which are loaded and visualized in Jupyter notebooks. 

| Script Name | Applicable Models | Remark |
|:----:|:-----:|:----|
| cifar10c | CIFAR10 | Required CIFAR10-C to be at `./datasets/CIFAR-10-C` |
| mnistc | MNIST | Required MNIST-C to be at `./datasets/mnist_c` |
| salt pepper noise | MNIST, FashionMNIST |

In general, these scripts take models from a path specified by the user. Wildcard can be used in this path. Please use `-h` option for further details of each command.

#### Example
Running the command below will take models from the directory and compute CIFAR10-C accuracies accordingly.

```./pyrun.sh ./scripts/cifar10c-analysis.py "./artifacts/experiment-robustness-cifar10-beta03/*/*"```

## Experiment Artifacts
Each experiment is assigned with a unique name:

```
<architecture>-<class_loss>-<cov_type>-<dataset>--<timestamp>
```

During training, we collect metrics to TensorBoard under `log` directory. These metrics include:
- loss
- accuracy
- I(X; Z) Bound (or something similar)
- I(Y; Z) Bound

When the bottleneck dimensions is `2`, we also plot the latent representation for 1000 test samples to TensorBoard.

We also save the details of each experiment in `summary.yml`.


## References
- [Alemi et al. (2016), Variational Information Bottleneck](https://arxiv.org/abs/1612.00410)
- [Cvitkovic et al. (2019), Minimal Achievable Sufficient Statistic Learning](https://arxiv.org/abs/1905.07822)
- [Mu et al. (2019), MNISTC](https://arxiv.org/abs/1906.02337)
- [Hendrycks et al. (2019), CIFAR10-C](https://zenodo.org/record/2535967)
