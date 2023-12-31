# -*- coding: utf-8 -*-
"""Wafer_Equation.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1s3KDy9pDhuvcBMik3V6T3atI_L4hygig
"""

import sys

import torch
import torch.nn as nn

import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
from collections import OrderedDict

from google.colab import drive
drive.mount("/content/gdrive")
data_dir = "/content/gdrive/MyDrive/CMP/Data"

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

class Swish(nn.Module):
    def __init__(self, inplace=True):
        super(Swish, self).__init__()
        self.inplace = inplace

    def forward(self, x, ):
      x = x.mul_(torch.sigmoid(x))

      return x


class DNN(torch.nn.Module):
    def __init__(self, layers):
        super(DNN, self).__init__()

        # parameters
        self.depth = len(layers) - 1

        # set up layer order dict
        self.activation = nn.Tanh()

        layer_list = list()
        for i in range(self.depth - 1):
            layer_list.append(
                ('layer_%d' % i, torch.nn.Linear(layers[i], layers[i+1]))
            )
            layer_list.append(('activation_%d' % i, self.activation))

        layer_list.append(
            ('layer_%d' % (self.depth - 1), torch.nn.Linear(layers[-2], layers[-1]))
        )
        layerDict = OrderedDict(layer_list)

        # deploy layers
        self.layers = torch.nn.Sequential(layerDict)

    def forward(self, x):
        out = self.layers(x)
        return out

class PhysicsInformedNN():
    def __init__(self, R_coll, R_train, W_train, Q_train, P_train, R_val, W_val, Q_val, P_val, K, layers):

        self.r_coll = torch.tensor(R_coll, requires_grad=True).float().to(device)

        self.r_train = torch.tensor(R_train, requires_grad=True).float().to(device)
        self.w_train = torch.tensor(W_train).float().to(device)
        self.q_train = torch.tensor(Q_train).float().to(device)
        self.p_train = torch.tensor(P_train).float().to(device)

        self.r_val = torch.tensor(R_val).float().to(device)
        self.w_val = torch.tensor(W_val).float().to(device)
        self.q_val = torch.tensor(Q_val).float().to(device)
        self.p_val = torch.tensor(P_val).float().to(device)

        self.K = torch.tensor(K).float().to(device)

        self.dnn_w = DNN(layers).to(device)
        self.dnn_q = DNN(layers).to(device)
        self.dnn_p = DNN(layers).to(device)

        self.criterion = nn.MSELoss()

        self.optimizer_w = torch.optim.Adam(self.dnn_w.parameters(), lr=1e-5, betas = (0.9,0.99),eps = 10**-15)
        self.optimizer_q = torch.optim.Adam(self.dnn_q.parameters(), lr=1e-5, betas = (0.9,0.99),eps = 10**-15)
        self.optimizer_p = torch.optim.Adam(self.dnn_p.parameters(), lr=1e-5, betas = (0.9,0.99),eps = 10**-15)

        self.iter = 0


    def w_net(self, r):
      w = self.dnn_w(r)
      return w

    def q_net(self, r):
      q = self.dnn_q(r)
      return q

    def p_net(self, r):
      p = self.dnn_p(r)
      return p


    def net(self, r):
      w = self.w_net(r)
      q = self.q_net(r)
      p = self.p_net(r)
      return w, q, p

    def net_eqn(self, r):

      w_coll, q_coll, p_coll = self.net(r)

      w_r = torch.autograd.grad(
          w_coll, r,
          grad_outputs=torch.ones_like(w_coll),
          retain_graph=True,
          create_graph=True
      )[0]

      w_rr = torch.autograd.grad(
          w_r, r,
          grad_outputs=torch.ones_like(w_coll),
          retain_graph=True,
          create_graph=True
      )[0]

      w_rrr = torch.autograd.grad(
          w_rr, r,
          grad_outputs=torch.ones_like(w_coll),
          retain_graph=True,
          create_graph=True
      )[0]

      w_rrrr = torch.autograd.grad(
          w_rrr, r,
          grad_outputs=torch.ones_like(w_coll),
          retain_graph=True,
          create_graph=True
      )[0]


      f = w_rrrr + (2/r)*w_rrr - (1/r**2)*w_rr + (1/r**3)*w_r + w_coll + p_coll/K - q_coll/K
      return f


    def train(self):

        self.optimizer_w.zero_grad()
        self.optimizer_q.zero_grad()
        self.optimizer_p.zero_grad()

        w_data_pred, q_data_pred, p_data_pred = self.net(self.r_train)
        f_pred = self.net_eqn(self.r_coll)

        data_loss = self.criterion(w_data_pred, self.w_train) + self.criterion(p_data_pred, self.p_train) + self.criterion(q_data_pred, self.q_train)
        res_loss = self.criterion(f_pred, torch.zeros_like(f_pred))
        loss = data_loss + res_loss

        loss.backward()
        self.optimizer_w.step()
        self.optimizer_q.step()
        self.optimizer_p.step()

        return data_loss, res_loss


    def validate(self):
      loss = 1

      with torch.no_grad():

        w_data_pred, q_data_pred, p_data_pred = self.net(self.r_val)
        # f_pred = self.net_eqn(self.r_coll)

        data_loss = self.criterion(w_data_pred, self.w_val) + self.criterion(p_data_pred, self.p_val) + self.criterion(q_data_pred, self.q_val)
        # res_loss = self.criterion(f_pred, torch.zeros_like(f_pred))
        loss = data_loss

      return loss


    def run(self, epochs):

      for epoch in range(epochs):

        data_loss, res_loss = self.train()

        if epoch % 20 == 0:
            print(
                'It: %d, Data Loss: %.3f, Residual Loss: %.3f' %
                (epoch,
                 data_loss.item(),
                 res_loss.item()
                )
            )
        if epoch % 100 == 0:
          val_loss = self.validate()
          print(
                'It: %d, Val Data Loss: %.3f' %
                (epoch,
                  val_loss.item())
            )




    def test(self, p_target):

      with torch.no_grad():
        w_data_pred, q_data_pred, p_data_pred = self.net(self.r_coll)

      p_pred = p_data_pred.detach().cpu().numpy()
      r_coll = self.r_coll.detach().cpu().numpy()

      plt.figure(figsize=(8, 6))
      plt.plot(r_coll, p_pred, label='Pred', color='blue')
      plt.plot(r_coll, p_target, label='Ground Truth', color='red')

      plt.xlabel('R (m)')
      plt.ylabel('P (Pa)')
      plt.title('Prediction vs Ground Truth')
      plt.legend()
      plt.show()

y_data = np.load(data_dir+"/cmp_Y.npy")[1,:,:]

center_r = 4e-2
innert_r = center_r + 1e-2

R = y_data[:,0]
R = R[np.where(R<0.099)][:,None] + 0.001
P = y_data[:,-2][:R.shape[0]][:,None]
W = y_data[:,-1][:R.shape[0]][:,None]
Q = 2*np.ones(R.shape[0])[:,None]*6894.76

R_star = R / 0.1
P_star = P / Q.max()
W_star = W / W.max()
Q_star = Q / Q.max()

num_points = 1500
rand_idx = np.random.choice(R.shape[0], num_points, replace=False)
rand_idx_train, rand_idx_val =  rand_idx[:int(num_points*0.8)], rand_idx[int(num_points*0.8):]

R_coll = R_star

R_train = R_star[rand_idx_train, :]
P_train = P_star[rand_idx_train, :]
W_train = W_star[rand_idx_train, :]
Q_train = Q_star[rand_idx_train, :]

R_val = R_star[rand_idx_val, :]
P_val = P_star[rand_idx_val, :]
W_val = W_star[rand_idx_val, :]
Q_val = Q_star[rand_idx_val, :]


E = 1.69*10**11
t = 5*10**-4
v = 0.27851

K = E*(t**3)/(12*(1-v**2))

layers = [1, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 1]

model = PhysicsInformedNN(R_coll, R_train, W_train, Q_train, P_train, R_val, P_val, W_val, Q_val, K, layers)

R_train

model.run(20000)

model.test(P_star)