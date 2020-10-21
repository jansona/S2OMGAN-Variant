import sys, os, cv2, time, math, json, re, hashlib
import torch
from glob import glob
import numpy as np
from PIL import Image
from math import sin, cos, asin, acos, pi
from options.test_options import TestOptions
from data import create_dataset
from models import create_model
from util import html
from scipy.signal import convolve2d
from util.visualizer import save_images, util as v_util
from data.base_dataset import BaseDataset, get_params, get_transform
# import util

# 地图尺度与坐标位宽的映射
zoom2width = {
    17: 6,
    18: 6
}

# 地球平均半径，以米为单位
R_earth = 6371004

def integrate_tiles(d_name, tile_mat: [[str]]) -> np.array:

    for line in tile_mat:
        for tile in line:
            if not os.path.exists("{}/{}".format(d_name, tile)):
                print(d_name, tile)
    
    def assemble_row(row_files: [str]) -> np.array:
        
        tile_cated = cv2.imread(os.path.join(d_name, row_files[0]))
        
        for file in row_files[1:]:
            temp_tile = cv2.imread(os.path.join(d_name, file))
            array_temp = np.array(temp_tile)
            if array_temp.ndim == 0:
                break
            tile_cated = np.concatenate((tile_cated, temp_tile), axis=1)
            
        return tile_cated
    
    rows = []
    
    for row in tile_mat:
        rows.append(assemble_row(row))
        
    map_cated = rows[0]
    
    for row in rows[1:]:
        map_cated = np.concatenate((row, map_cated), axis=0)
        
    return map_cated

def statis_value(in_path):
    name_list = os.listdir(in_path)
    name_list = list(filter(lambda x: re.match("\d+_\d+.png", x), name_list))
    y_list = []
    x_list = []
    for name in name_list:
        name = name.split("/")[-1]
        name = name.split(".")[0]
        a = name.split('_',2)
        y_list.append(int(a[0]))
        x_list.append(int(a[1]))
    x_min,x_max = min(x_list),max(x_list)
    y_min,y_max = min(y_list),max(y_list)
    return x_min,x_max,y_min,y_max

def num2deg(x, y, zoom):
    '''这个地方有错误，关于形参与实参的位置'''
    n = 2**zoom
    lon_deg = x/n*360.0-180.0
    lat_deg = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat_deg = lat_deg*180.0/math.pi
    return [lon_deg, lat_deg]


def batch_generate(params):

    sys.argv = params

    opt = TestOptions().parse()  # get test options
    opt.dataroot = opt.DATA_PATH
#     opt.epoch = 200
    # hard-code some parameters for test
    opt.num_threads = 0   # test code only supports num_threads = 1
    #opt.batch_size = 1    # test code only supports batch_size = 1
    opt.serial_batches = True  # disable data shuffling; comment this line if results on randomly chosen images are needed.
    opt.no_flip = True    # no flip; comment this line if results on flipped images are needed.
    opt.load_size = opt.crop_size
    opt.display_id = -1   # no visdom display; the test code saves the results to a HTML file.
    dataset = create_dataset(opt)  # create a dataset given opt.dataset_mode and other options
    model = create_model(opt)      # create a model given opt.model and other options
    # load model from a path - for platform
    load_path = opt.MODEL_FILE
    net = getattr(model, 'netG_A')
    if isinstance(net, torch.nn.DataParallel):
        net = net.module
    print('loading the model from %s' % load_path)
    state_dict = torch.load(load_path, map_location=str(model.device))
    if hasattr(state_dict, '_metadata'):
        del state_dict._metadata
    # patch InstanceNorm checkpoints prior to 0.4
    for key in list(state_dict.keys()):  # need to copy keys here because we mutate in loop
        model._BaseModel__patch_instance_norm_state_dict(state_dict, net, key.split('.'))
    net.load_state_dict(state_dict)
    model.print_networks(opt.verbose)
    
    # create a website
    sha = hashlib.sha256()
    sha.update(str(time.time()).encode('utf-8'))
    web_dir = opt.OUTPUT_PATH + "/" + sha.hexdigest()# specific output dir - for platform
    webpage = html.HTML(web_dir, 'Experiment = %s, Phase = %s, Epoch = %s' % (opt.name, opt.phase, opt.epoch))
    # test with eval mode. This only affects layers like batchnorm and dropout.
    # For [pix2pix]: we use batchnorm and dropout in the original pix2pix. You can experiment it with and without eval() mode.
    # For [CycleGAN]: It should not affect CycleGAN as CycleGAN uses instancenorm without dropout.
    starttime = time.time()
    lasttime = starttime
    
    if opt.eval:
        model.eval()
    starttime = time.time()
    for i, data in enumerate(dataset):
        if i >= opt.num_test:  # only apply our model to opt.num_test images.
            break
        model.set_input(data)  # unpack data from data loader
        model.test()           # run inference
        # visuals = model.get_current_visuals()  # get image results
        # img_path = model.get_image_paths()     # get image paths
        # if i > 0 and (i + 1) % 10 == 0:  # save images to an HTML file
        #     print('processing (%04d)-th image... %s' % (len(img_path)+(i)*opt.batch_size, ''), 'cost', time.time()-lasttime, 'seconds')
        #     lasttime = time.time()
        # save_images(webpage, visuals, img_path, aspect_ratio=opt.aspect_ratio, width=opt.display_winsize)
        visual = model.real_B
        img_path = model.img_paths
        print(img_path, web_dir)

    # webpage.save()  # save the HTML
    print("Work Done!!!")
    print('Generated', len(dataset), 'maps. Total Time Cost: ', lasttime - starttime, 'seconds')

    return web_dir


def predict_function(params):

    sys.argv = params
    sys.argv.extend(['--gpu_ids', '-1'])
    opt = TestOptions().parse()  # get test options
    opt.name = "demo_pretrained"
#     opt.epoch = 200
    # hard-code some parameters for test
    opt.num_threads = 0   # test code only supports num_threads = 1
    #opt.batch_size = 1    # test code only supports batch_size = 1
    opt.serial_batches = True  # disable data shuffling; comment this line if results on randomly chosen images are needed.
    opt.no_flip = True    # no flip; comment this line if results on flipped images are needed.
    opt.load_size = opt.crop_size
    opt.display_id = -1   # no visdom display; the test code saves the results to a HTML file.
#     dataset = create_dataset(opt)  # create a dataset given opt.dataset_mode and other options
    model = create_model(opt)      # create a model given opt.model and other options
#     model.setup(opt)               # regular setup: load and print networks; create schedulers

    load_path = opt.MODEL_FILE
    net = getattr(model, 'netG_A')
    if isinstance(net, torch.nn.DataParallel):
        net = net.module
    print('loading the model from %s' % load_path)
    state_dict = torch.load(load_path, map_location=str(model.device))
    if hasattr(state_dict, '_metadata'):
        del state_dict._metadata
    # patch InstanceNorm checkpoints prior to 0.4
    for key in list(state_dict.keys()):  # need to copy keys here because we mutate in loop
        model._BaseModel__patch_instance_norm_state_dict(state_dict, net, key.split('.'))
    net.load_state_dict(state_dict)
    model.print_networks(opt.verbose)

    starttime = time.time()
    lasttime = starttime

    if opt.eval:
        model.eval()
    starttime = time.time()
    
    print(opt.IMAGE_PATH, opt.RESULT_PATH)
    source_path = opt.IMAGE_PATH

    if os.path.isdir(source_path):
        opt.RESULT_PATH = opt.RESULT_PATH.split('.')[0] + '.tif'
        result_dir_path = '/'.join(opt.RESULT_PATH.split('/')[:-1])
        temp_img_paths = []
        temp_suffix_name = glob("{}/*".format(source_path))[0].split('.')[-1]

        fake_params = list()
        fake_params.extend(['XXX.py', '--MODEL_FILE', opt.MODEL_FILE, '--DATA_PATH', source_path,
            '--OUTPUT_PATH', result_dir_path, '--model', opt.model, '--dataset_mode', 'bare'])
        web_dir = batch_generate(fake_params)

        # # automatic integrate and autocontrast - for platform
        # print("start integrating...")
        
        # # in_path = webpage.get_image_dir()
        # in_path = result_dir_path 
        # # out_path = in_path[:-6] + "integrated"
        # out_path = in_path
        # if not os.path.exists(out_path):
        #     os.makedirs(out_path)

        # x_min, x_max, y_min, y_max = statis_value(in_path)
        # x_size = x_max - x_min + 1
        # y_size = y_max - y_min + 1
        # zoom = opt.zoom
        # coord_width = zoom2width[zoom]
                
        # base_path = in_path + "/"
        # file_template = "{:0%dd}_{:0%dd}." %(coord_width, coord_width) + temp_suffix_name
        # tile_files = []
        # for i in range(x_size):
        #     temp_list = []
        #     for j in range(y_size):
        #         temp_list.append(file_template.format(y_min + j, x_min + i))
                
        #     tile_files.append(temp_list)
    
        # map_pic = integrate_tiles(result_dir_path, tile_files)
        # cv2.imwrite(opt.RESULT_PATH, map_pic)

    else:
        input_img = Image.open(opt.IMAGE_PATH).convert('RGB')
        transform_params = get_params(opt, input_img.size)
        transformer = get_transform(opt, transform_params, grayscale=(opt.input_nc == 1))
        x = transformer(input_img)
    #     print(type(x), x.shape, x)
        
        model.real_A = x.unsqueeze(0).to(model.device)
        model.forward()
        x = model.fake_B[0]
    #     print(type(x), x.shape, x)

        x = (np.transpose(x.detach().numpy(), (1, 2, 0)) + 1) / 2.0 * 255.0
        x = x.astype(np.uint8)

        outimg = Image.fromarray(x)
        outimg = outimg.resize(input_img.size)
        outimg.save(opt.RESULT_PATH)


if __name__ == '__main__':

    predict_function(sys.argv)
