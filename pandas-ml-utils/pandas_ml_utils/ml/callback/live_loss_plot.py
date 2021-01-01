from typing import Tuple, List

from pandas_ml_common import LazyInit


class NbLiveLossPlot(object):

    def __init__(self, figsize: Tuple[int] = None, frequency: int = 10, plot_reconstruction: bool = False, backend: str = 'nbAgg'):
        self.frequency = frequency
        self.count = 0
        self.x = []
        self.train_loss = []
        self.val_loss = []

        # initialize a plot make sure backend is not inline but nbAgg
        import matplotlib.pyplot as plt
        if backend is not None:
            plt.switch_backend(backend.replace('notebook', 'nbAgg'))

        self.fig, self.ax = plt.subplots(2 if plot_reconstruction else 1, 2, figsize=figsize)
        self.ax = self.ax.flatten()
        self.fig.show()

        # from IPython.display import display
        # display(self.fig)

    def __call__(self, epoch, fold, fold_epoch, loss, val_loss, y_train, y_test: List, y_hat_train: LazyInit, y_hat_test: List[LazyInit]):
        # print(epoch, fold, fold_epoch, loss, val_loss)
        self.count += 1
        self.x.append(self.x[-1] + 1 if len(self.x) > 0 else 0)
        self.train_loss.append(loss)
        self.val_loss.append(val_loss)

        if self.count % self.frequency == 0:
            for x in self.ax: x.clear()
            self.ax[0].plot(self.x, self.train_loss)
            self.ax[1].plot(self.x, self.val_loss)
            if len(self.ax) > 2:
                self.ax[2].plot(y_train)
                self.ax[2].plot(y_hat_train())
                if len(y_test) > 0:
                    self.ax[3].plot(y_test[0])
                    self.ax[3].plot(y_hat_test[0]())

                self.fig.canvas.draw()
            self.fig.canvas.draw()

