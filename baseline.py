# -*- coding: utf-8 -*-

"""
@File: model.py
@Author: Chance (Qian Zhen)
@Description: Baseline of neural network model based on PyTorch.
@Date: 2020/12/19
"""

import time
import torch
from scipy import stats
import numpy as np
from torch import nn, optim
from typing import Generator, Union
from utils import check_device, plot_curve, calculate_classification_score, InvalidArguments
from torch.optim.lr_scheduler import CosineAnnealingWarmRestarts
import albumentations as A

trfm = A.Compose([
    A.HorizontalFlip(p=0.5),
    A.Rotate(limit=(0, 45)),
    A.GaussNoise()
])

class Model:
    def __init__(self, model: nn.Module, device: str = "gpu") -> None:
        self.model = model
        self.device = check_device(device)

    def fit(
            self,
            train_iter: Generator,
            validation_iter: Generator,
            lr: float = 0.01,
            loss_criterion: Union[str, nn.Module] = "cross_entropy",
            optimizer: Union[str, optim.Optimizer] = "sgd",
            num_epochs: int = 30,
            checkpoint_epochs: int = None,
            model_save_path: str = None,
            is_plot: bool = False
    ) -> None:
        print("training on %s" % self.device)
        self.model = self.model.to(self.device)

        if train_iter is None or validation_iter is None:
            raise InvalidArguments("Must input training data and validation data!")

        if isinstance(loss_criterion, str):
            if loss_criterion.lower() == "cross_entropy":
                loss_criterion = torch.nn.CrossEntropyLoss()

        if isinstance(optimizer, str):
            if optimizer.lower() == "sgd":
                optimizer = optim.SGD(self.model.parameters(), lr=lr, weight_decay=0.001)

        # Learning rate scheduler
        # scheduler = CosineAnnealingWarmRestarts(optimizer, T_0=10, T_mult=2)
        train_acc_list, valid_acc_list = [], []

        # If checkpoint_epochs is not None, it means that model will continue to train from last weights.
        epoch_iter = range(num_epochs, num_epochs + checkpoint_epochs) if checkpoint_epochs else range(num_epochs)
        for epoch in epoch_iter:
            n, batch_count, train_loss_sum, train_acc_sum, start = 0, 0, 0.0, 0.0, time.time()
            self.model.train()

            for idx, (X, y) in enumerate(train_iter):
                X = X.to(self.device)
                y = y.to(self.device)

                y_pred = self.model(X)
                loss = loss_criterion(y_pred, y)

                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                # scheduler.step(epoch + idx / len(train_iter))

                train_loss_sum += loss.cpu().item()
                train_acc_sum += (y_pred.argmax(dim=1).cpu() == y.cpu()).sum()

                batch_count += 1
                n += y.shape[0]
            valid_acc, valid_loss = self.evaluation(validation_iter, "Accuracy", loss_criterion)

            train_acc_list.append(train_acc_sum / n)
            valid_acc_list.append(valid_acc)
            print("epoch %d, train_loss %.4f, valid_loss %.4f, train acc %.3f, valid_total acc %.3f, time %.1f sec"
                  % (epoch + 1, train_loss_sum / batch_count, valid_loss, train_acc_sum / n, valid_acc, time.time() - start))

            if model_save_path:
                torch.save(
                    self.model.state_dict(),
                    "%s/epoch%d_trainloss%.3f_validloss%.3f_trainacc%.3f_validacc%.3f.pth"
                    % (model_save_path,
                       epoch + 1,
                       train_loss_sum / batch_count,
                       valid_loss,
                       train_acc_sum / n,
                       valid_acc)
                )

        if is_plot:
            plot_curve(
                train_acc_list,
                valid_acc_list,
                "Training accuracy",
                "Validation accuracy",
                "Epochs",
                "Accuracy"
            )

    def predict(self, X: torch.Tensor) -> list:
        self.model = self.model.to(self.device)
        X = X.to(self.device)
        self.model.eval()

        with torch.no_grad():
            return self.model(X).argmax(dim=1).cpu().tolist()

    def evaluation(self, test_iter: Generator, score: str, loss_criterion=None, TTA=False):
        y_true, y_pred = [], []
        eval_loss_sum = 0
        batch_count = 0
        for X, y in test_iter:
            y_true.extend(y.tolist())
            if TTA:
                # print(X.shape)
                for single_X in X:
                    trfm_X_1 = torch.tensor(trfm(image=single_X.numpy())["image"]).unsqueeze(0)
                    trfm_X_2 = torch.tensor(trfm(image=single_X.numpy())["image"]).unsqueeze(0)
                    trfm_X_3 = torch.tensor(trfm(image=single_X.numpy())["image"]).unsqueeze(0)
                    trfm_X_4 = torch.tensor(trfm(image=single_X.numpy())["image"]).unsqueeze(0)
                    trfm_X_5 = torch.tensor(trfm(image=single_X.numpy())["image"]).unsqueeze(0)
                    pred_y_1 = self.predict(trfm_X_1)
                    pred_y_2 = self.predict(trfm_X_2)
                    pred_y_3 = self.predict(trfm_X_3)
                    pred_y_4 = self.predict(trfm_X_4)
                    pred_y_5 = self.predict(trfm_X_5)
                    pred_y_list = [pred_y_1, pred_y_2, pred_y_3, pred_y_4, pred_y_5]
                    y_pred.append(stats.mode(pred_y_list)[0][0])

            else:
                y_pred.extend(self.predict(X))
                if loss_criterion:
                    self.model.eval()
                    with torch.no_grad():
                        eval_loss_sum += loss_criterion(self.model(X.to(self.device)), y.to(self.device))
                batch_count += 1

        score = calculate_classification_score(y_true, y_pred, score)

        if loss_criterion:
            return score, eval_loss_sum / batch_count
        return score