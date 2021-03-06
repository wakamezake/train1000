#!/usr/bin/env python
# -*- coding: utf-8 -*-

from keras import backend as K
K.set_image_data_format('channels_last')

from keras.models import Model
from keras.layers import Flatten, Conv2D, Dropout, Average, Multiply, Input, Activation, Lambda, GlobalAveragePooling2D
from keras.optimizers import Adam
from keras.preprocessing.image import ImageDataGenerator
from keras.regularizers import l2

import numpy as np

import os
import sys

if( not os.path.exists( 'WiG/keras/activation.py' ) ):
	import subprocess
	cmd = 'git clone https://github.com/mastnk/WiG'
	subprocess.call(cmd.split())
	
sys.path.append('WiG/keras')
import activation


##### model #####
def build_model( nb_layers = 3, dropout = 0, nb_features=64, Wl2=0, nb_classes = 10, input_shape = (32,32,3) ):
	inp = Input(shape=input_shape)
	x = inp
	
	yy = []
	for i in range(nb_layers):
		y = Conv2D( nb_features, (3,3), kernel_initializer='he_normal', kernel_regularizer=l2(Wl2) ) (x)
		m = Conv2D( nb_features, (3,3), kernel_initializer='zeros', activation='sigmoid' ) (x)
		x = Multiply() ([m,y])
		
		y = Conv2D( nb_classes, (3,3), kernel_initializer='zeros', kernel_regularizer=l2(Wl2), use_bias=False ) (x)
		m = Conv2D( nb_classes, (3,3), kernel_initializer='zeros', activation='sigmoid' ) (x)
		y = Multiply() ([m,y])

		if( dropout > 0 ):
			y = Dropout(dropout) (y)
		
		y = GlobalAveragePooling2D() (y)
		
		yy.append(y)
	
	y = Average() (yy)
	
	y = Activation('softmax')(y)
	return Model(inputs=inp, outputs=y)

##### generator #####
def aug_color(X):
	a = np.random.uniform( 0.95, 1.05, size=(X.shape[0],1,1,1) )
	X *= a
	a = np.random.uniform( 0.95, 1.05, size=(X.shape[0],1,1,1) )
	X *= a
		
	a = np.random.uniform( 0.95, 1.05, size=(X.shape[0],1,1,1) )
	b = np.random.uniform( -0.005, +0.005, size=(X.shape[0],1,1,1) )
	X = X * a + b - (a-1.0)/2.0
	return X

def build_generator( X_train, Y_train, batch_size, gen = None ):
	if( gen == None ):
		gen = ImageDataGenerator(width_shift_range=0.25, height_shift_range=0.25, horizontal_flip=True, rotation_range=5.0, zoom_range=[0.99, 1.05], shear_range=3.14/180)
	gen.fit(X_train)
	flow = gen.flow(X_train, Y_train, batch_size=batch_size)
	flow_batch_size = batch_size
	if( flow_batch_size > X_train.shape[0] ):
		flow_batch_size = X_train.shape[0]
	flow = gen.flow(X_train, Y_train, batch_size=flow_batch_size)
	Xque, Yque = flow.__next__()
	Xque = aug_color(Xque)
	
	while(True):
		while( Xque.shape[0] < batch_size ):
			_X, _Y = flow.__next__()
			_X = aug_color(_X)
			Xque = np.concatenate( (Xque, _X), axis=0 )
			Yque = np.concatenate( (Yque, _Y), axis=0 )
		
		X = Xque[:batch_size, :]
		Y = Yque[:batch_size, :]
		
		Xque = Xque[batch_size:, :]
		Yque = Yque[batch_size:, :]
		
		yield X, Y


def gen_mixup( x, y, batch_size, mixup_alpha = 0.2 ):
	_gen = build_generator( x, y, 2*batch_size )
	while( True ):
		x, y = _gen.__next__()
		
		L = np.random.beta( mixup_alpha, mixup_alpha, size=(batch_size,1) )
		LX = L.reshape(batch_size, 1, 1, 1)
		LY = L.reshape(batch_size, 1)
		x = LX * x[:batch_size,:] + (1-LX) * x[batch_size:,:]
		y = LY * y[:batch_size,:] + (1-LY) * y[batch_size:,:]
		
		yield x, y

if( __name__ == '__main__' ):
	from keras.callbacks import CSVLogger, ModelCheckpoint
	from keras.optimizers import Adam
	from keras.models import load_model
	import train1000
	import os
	import sys

	def error_exit():
		print( '!!!!! ERROR !!!!!' )
		print( 'Usage: python {name} [10|100]'.format(name=sys.argv[0]) )
		sys.exit()

	try:
		title, ext = os.path.splitext(sys.argv[0])
		nb_classes = int(sys.argv[1])
	except:
		error_exit()
	
	title += '{nb_classes:d}'.format(nb_classes=nb_classes)

	epochs = 100
	steps_per_epoch = 100
	
	batch_size = 1000
	
	nb_layers = 5

	nb_features = 64
	dropout = 0.5
	Wl2 = 1E-6

	if( nb_classes == 10 ):
		(X_train, Y_train), (X_test, Y_test) = train1000.cifar10()
	elif( nb_classes == 100 ):
		(X_train, Y_train), (X_test, Y_test) = train1000.cifar100()
	else:
		error_exit()
	
	model = build_model( nb_classes = nb_classes, nb_layers = nb_layers, dropout = dropout, nb_features = nb_features, Wl2=Wl2 )
	opt = Adam(decay=1.0/(epochs*steps_per_epoch))
	model.compile(loss='categorical_crossentropy', optimizer=opt, metrics=['categorical_crossentropy', 'accuracy'])
	
	if( not os.path.exists( title+'.hdf5' ) ):
		gen = gen_mixup( X_train, Y_train, batch_size, batch_size )

		flog = open( title+'.csv', 'w' )

		line = 'epoch, categorical_crossentropy, accuracy, val_categorical_crossentropy, val_accuracy, save'
		print( line )
		flog.write( line+'\n' )
		flog.flush()
	
		min_crossentropy = None
		for epoch in range(epochs):
			for step in range(steps_per_epoch):
				x, y = gen.__next__()
				model.train_on_batch( x, y )
			
			eva = model.evaluate( X_train, Y_train, verbose=0 )
			crossentropy = eva[1]
			accuracy = eva[2]
			
			eva = model.evaluate( X_test, Y_test, verbose=0 )
			val_crossentropy = eva[1]
			val_accuracy = eva[2]
			
			if( min_crossentropy == None or min_crossentropy > crossentropy ):
				min_crossentropy = crossentropy
				model.save( title+'.hdf5' )
				save = '*'
			else:
				save = '-'
			
			line = '{epoch}, {crossentropy}, {accuracy}, {val_crossentropy}, {val_accuracy}, {save}'.format(epoch=epoch, crossentropy=crossentropy, accuracy=accuracy, val_crossentropy=val_crossentropy, val_accuracy=val_accuracy, save=save)
			print( line )
			flog.write( line+'\n' )
			flog.flush()
		
		flog.close()
		
	model.load_weights( title+'.hdf5' )
	
	print( 'train data:' )
	eva = model.evaluate( X_train, Y_train, verbose=0 )
	for i in range(1,len(model.metrics_names)):
		print( model.metrics_names[i] + ' : ', eva[i] )

	print()

	print( 'test data:' )
	eva = model.evaluate( X_test, Y_test, verbose=0 )
	for i in range(1,len(model.metrics_names)):
		print( model.metrics_names[i] + ' : ', eva[i] )
