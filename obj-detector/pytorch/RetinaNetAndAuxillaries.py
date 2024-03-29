# -*- coding: utf-8 -*-
"""
Created on Mon Sep 23 14:09:03 2019

@author: Alex
"""

from fastai.vision import *
import json
import numpy as np
from pathlib import Path

import matplotlib.cm as cmx
import matplotlib.colors as mcolors
from cycler import cycler

def get_data(bs, size):
    """AB:
       bs is batch size, size is width of square transformed image (and BBox)
       tfm_y is transfrom y data (which is target mask, or: bounding box)
       collate_fn=bb_pad_collate for collating the data into a mini-batch!!!"""
    src = ObjectItemList.from_folder(path/'train') # train+val images
    src = src.split_by_files(val_images) # split by fname ['00001.jpg', ...]
    src = src.label_from_func(get_y_func) # assign labels
    src = src.transform(get_transforms(), size=size, tfm_y=True)
    return src.databunch(path=path, bs=bs, collate_fn=bb_pad_collate)
  
class LateralUpsampleMerge(nn.Module):
    "Merge the features coming from the downsample path (in `hook`) with the upsample path."
    def __init__(self, ch, ch_lat, hook):
        super().__init__()
        self.hook = hook
        self.conv_lat = conv2d(ch_lat, ch, ks=1, bias=True)
    
    def forward(self, x):
      "AB: Defines the computation performed at every call."
      return self.conv_lat(self.hook.stored) + F.interpolate(x, 
                                    self.hook.stored.shape[-2:], mode='nearest')

# RetinaNet original implementation
class RetinaNet(nn.Module):
    "Implements RetinaNet from https://arxiv.org/abs/1708.02002"
    def __init__(self, encoder:nn.Module, n_classes, final_bias=0., chs=256, 
                 n_anchors=9, flatten=True):
      
        super().__init__()
        self.n_classes,self.flatten = n_classes,flatten
        imsize = (256,256) # AB: imsize is hard coded!!!??? not self.imsize!
        
        # AB: retrieve model sizes for given imsize
        sfs_szs = model_sizes(encoder, size=imsize)
        # AB: "Get the indexes of the layers where the size of the activation changes."
        sfs_idxs = list(reversed(_get_sfs_idxs(sfs_szs)))
        # AB: define hook_layers for layers with changing size of activation
        # AB: for later skipping contacts
        self.sfs = hook_outputs([encoder[i] for i in sfs_idxs])
        
        # AB: encoder = create_body(models.resnet50, cut=-2), feature layer substracted
        self.encoder = encoder
        # AB: top 2 layers of encoding block C5
        self.c5top5 = conv2d(sfs_szs[-1][1], chs, ks=1, bias=True)
        self.c5top6 = conv2d(sfs_szs[-1][1], chs, stride=2, bias=True)
        # AB: top layer of decoding layer P6
        self.p6top7 = nn.Sequential(nn.ReLU(), conv2d(chs, chs, stride=2, bias=True))
        # AB: "Merge the features coming from the downsample path (in `hook`) with the upsample path."
        # AB: merge layer for every 
        self.merges = nn.ModuleList([LateralUpsampleMerge(chs, sfs_szs[idx][1], hook) 
                                     for idx,hook in zip(sfs_idxs[-2:-4:-1], self.sfs[-2:-4:-1])])
        # AB: why smoothers?!
        self.smoothers = nn.ModuleList([conv2d(chs, chs, 3, bias=True) for _ in range(3)])
        self.classifier = self._head_subnet(n_classes, n_anchors, final_bias, chs=chs)
        self.box_regressor = self._head_subnet(4, n_anchors, 0., chs=chs)
        
    def _head_subnet(self, n_classes, n_anchors, final_bias=0., n_conv=4, chs=256):
        "Helper function to create one of the subnet for regression/classification."
        layers  = [conv_layer(chs, chs, bias=True, norm_type=None) for _ in range(n_conv)]
        layers += [conv2d(chs, n_classes * n_anchors, bias=True)]
        layers[-1].bias.data.zero_().add_(final_bias)
        layers[-1].weight.data.fill_(0)
        return nn.Sequential(*layers)
    
    def _apply_transpose(self, func, p_states, n_classes):
        #Final result of the classifier/regressor is bs * (k * n_anchors) * h * w
        #We make it bs * h * w * n_anchors * k then flatten in bs * -1 * k so we can contenate
        #all the results in bs * anchors * k (the non flatten version is there for debugging only)
        if not self.flatten: 
            sizes = [[p.size(0), p.size(2), p.size(3)] for p in p_states]
            return [func(p).permute(0,2,3,1).view(*sz,-1,n_classes) for p,sz in zip(p_states,sizes)]
        else:
            return torch.cat([func(p).permute(0,2,3,1).contiguous().view(p.size(0),-1,n_classes) for p in p_states],1)
    
    def forward(self, x):
        # AB: x is input, which is image
        c5 = self.encoder(x)
        p_states = [self.c5top5(c5.clone()), self.c5top6(c5)]
        p_states.append(self.p6top7(p_states[-1]))
        for merge in self.merges: p_states = [merge(p_states[0])] + p_states
        for i, smooth in enumerate(self.smoothers[:3]):
            p_states[i] = smooth(p_states[i])
            
        return [self._apply_transpose(self.classifier, p_states, self.n_classes), 
                self._apply_transpose(self.box_regressor, p_states, 4),
                [[p.size(2), p.size(3)] for p in p_states]]
    
    def __del__(self):
        if hasattr(self, "sfs"): self.sfs.remove()
        
def create_grid(size):
    "Create a grid of a given `size`."
    H, W = size if is_tuple(size) else (size,size)
    grid = FloatTensor(H, W, 2)
    linear_points = torch.linspace(-1+1/W, 1-1/W, W) if W > 1 else tensor([0.])
    grid[:, :, 1] = torch.ger(torch.ones(H), linear_points).expand_as(grid[:, :, 0])
    linear_points = torch.linspace(-1+1/H, 1-1/H, H) if H > 1 else tensor([0.])
    grid[:, :, 0] = torch.ger(linear_points, torch.ones(W)).expand_as(grid[:, :, 1])
    return grid.view(-1,2)

def show_anchors(ancs, size):
    # AB changed into H, W format, ytickslabels hashed out
    H, W = size if is_tuple(size) else (size,size)
    
    _,ax = plt.subplots(1,1, figsize=(5,5))
    ax.set_xticks(np.linspace(-1,1, W+1))
    ax.set_yticks(np.linspace(-1,1, H+1))
    ax.grid()
    
    ax.scatter(ancs[:,1], ancs[:,0]) #y is first
    
    # ax.set_yticklabels([])
    # ax.set_xticklabels([])
    ax.set_xlim(-1,1)
    ax.set_ylim(1,-1) #-1 is top, 1 is bottom
    for i, (x, y) in enumerate(zip(ancs[:, 1], ancs[:, 0])): ax.annotate(i, xy = (x,y))
    
def create_anchors(sizes, ratios, scales, flatten=True):
    "Create anchor of `sizes`, `ratios` and `scales`."
    aspects = [[[s*math.sqrt(r), s*math.sqrt(1/r)] for s in scales] for r in ratios]
    aspects = torch.tensor(aspects).view(-1,2)
    anchors = []
    
    for h,w in sizes:
        # 4 here to have the anchors overlap.
        sized_aspects = 4 * (aspects * torch.tensor([2/h,2/w])).unsqueeze(0)
        base_grid = create_grid((h,w)).unsqueeze(1)
        n,a = base_grid.size(0), aspects.size(0)
        ancs = torch.cat([base_grid.expand(n,a,2), sized_aspects.expand(n,a,2)], 2)
        anchors.append(ancs.view(h,w,a,4))
    return torch.cat([anc.view(-1,4) for anc in anchors],0) if flatten else anchors

def get_cmap(N):
    color_norm  = mcolors.Normalize(vmin=0, vmax=N-1)
    return cmx.ScalarMappable(norm=color_norm, cmap='Set3').to_rgba

def draw_outline(o, lw):
    o.set_path_effects([patheffects.Stroke(
        linewidth=lw, foreground='black'), patheffects.Normal()])

#def draw_rect(ax, b, color='white'):
#    patch = ax.add_patch(patches.Rectangle(b[:2], *b[-2:], fill=False, edgecolor=color, lw=2))
#    draw_outline(patch, 4)

def draw_text(ax, xy, txt, sz=14, color='white'):
    text = ax.text(*xy, txt,
        verticalalignment='top', color=color, fontsize=sz, weight='bold')
    draw_outline(text, 1)
    
def show_boxes(boxes):
    "Show the `boxes` (size by 4)"
    _, ax = plt.subplots(1,1, figsize=(5,5))
    ax.set_xlim(-1,1)
    ax.set_ylim(1,-1)
    
    for i, bbox in enumerate(boxes):
        bb = bbox.numpy()
        rect = [bb[1]-bb[3]/2, bb[0]-bb[2]/2, bb[3], bb[2]]
        draw_rect(ax, rect, color=color_list[i%num_color])
        draw_text(ax, [bb[1]-bb[3]/2,bb[0]-bb[2]/2], str(i), color=color_list[i%num_color])

def activ_to_bbox(acts, anchors, flatten=True):
    "Extrapolate bounding boxes on anchors from the model activations."
    if flatten:
        acts.mul_(acts.new_tensor([[0.1, 0.1, 0.2, 0.2]])) #Can't remember where those scales come from, but they help regularize
        centers = anchors[...,2:] * acts[...,:2] + anchors[...,:2]
        sizes = anchors[...,2:] * torch.exp(acts[...,:2])
        return torch.cat([centers, sizes], -1)
    else: return [activ_to_bbox(act,anc) for act,anc in zip(acts, anchors)]
    return res

def cthw2tlbr(boxes):
    "Convert center/size format `boxes` to top/left bottom/right corners."
    top_left = boxes[:,:2] - boxes[:,2:]/2
    bot_right = boxes[:,:2] + boxes[:,2:]/2
    return torch.cat([top_left, bot_right], 1)

def intersection(anchors, targets):
    "Compute the sizes of the intersections of `anchors` by `targets`."
    ancs, tgts = cthw2tlbr(anchors), cthw2tlbr(targets)
    a, t = ancs.size(0), tgts.size(0)
    ancs, tgts = ancs.unsqueeze(1).expand(a,t,4), tgts.unsqueeze(0).expand(a,t,4)
    top_left_i = torch.max(ancs[...,:2], tgts[...,:2])
    bot_right_i = torch.min(ancs[...,2:], tgts[...,2:])
    sizes = torch.clamp(bot_right_i - top_left_i, min=0) 
    return sizes[...,0] * sizes[...,1]

def IoU_values(anchors, targets):
    "Compute the IoU values of `anchors` by `targets`."
    inter = intersection(anchors, targets)
    anc_sz, tgt_sz = anchors[:,2] * anchors[:,3], targets[:,2] * targets[:,3]
    union = anc_sz.unsqueeze(1) + tgt_sz.unsqueeze(0) - inter
    return inter/(union+1e-8)

def match_anchors(anchors, targets, match_thr=0.5, bkg_thr=0.4):
    "Match `anchors` to targets. -1 is match to background, -2 is ignore."
    # AB: returns the target box number to which the anchor is best matching
    matches = anchors.new(anchors.size(0)).zero_().long() - 2
    if targets.numel() == 0: return matches
    ious = IoU_values(anchors, targets)
    vals,idxs = torch.max(ious,1)
    matches[vals < bkg_thr] = -1
    matches[vals > match_thr] = idxs[vals > match_thr]
    #Overwrite matches with each target getting the anchor that has the max IoU.
    #vals,idxs = torch.max(ious,0)
    #If idxs contains repetition, this doesn't bug and only the last is considered.
    #matches[idxs] = targets.new_tensor(list(range(targets.size(0)))).long()
    return matches

def tlbr2cthw(boxes):
    "Convert top/left bottom/right format `boxes` to center/size corners."
    center = (boxes[:,:2] + boxes[:,2:])/2
    sizes = boxes[:,2:] - boxes[:,:2]
    return torch.cat([center, sizes], 1)

def bbox_to_activ(bboxes, anchors, flatten=True):
    "Return the target of the model on `anchors` for the `bboxes`."
    if flatten:
        t_centers = (bboxes[...,:2] - anchors[...,:2]) / anchors[...,2:] 
        t_sizes = torch.log(bboxes[...,2:] / anchors[...,2:] + 1e-8) 
        return torch.cat([t_centers, t_sizes], -1).div_(bboxes.new_tensor([[0.1, 0.1, 0.2, 0.2]]))
      
    else: return [activ_to_bbox(act,anc) for act,anc in zip(acts, anchors)] #AB: unnecessary? hashed out...
    return res #AB: unnecessary? hashed out...

def encode_class(idxs, n_classes):
    target = idxs.new_zeros(len(idxs), n_classes).float()
    mask = idxs != 0
    i1s = LongTensor(list(range(len(idxs))))
    target[i1s[mask],idxs[mask]-1] = 1
    return target

class RetinaNetFocalLoss(nn.Module):
    
    def __init__(self, gamma:float=2., alpha:float=0.25,  pad_idx:int=0, scales:Collection[float]=None, 
                 ratios:Collection[float]=None, reg_loss:LossFunction=F.smooth_l1_loss):
        # AB: gamma:float=2., the colon indicates the object type. For transporting in other languages...
        # AB: super is used to call method of base class (nn.Module) via delegation (=indirection)
        super().__init__()
        # store values in class object
        self.gamma,self.alpha,self.pad_idx,self.reg_loss = gamma,alpha,pad_idx,reg_loss
        self.scales = ifnone(scales, [1,2**(-1/3), 2**(-2/3)])
        self.ratios = ifnone(ratios, [1/2,1,2])
        
    def _change_anchors(self, sizes:Sizes) -> bool:
        # AB leading underscore for showing that this function should be private
        # AB "->", function annotation for describing the return value (handy for debugging)
        # AB hasattr() returns True if object class has attribute "sizes"
        if not hasattr(self, 'sizes'):
            return True
        for sz1, sz2 in zip(self.sizes, sizes):
            if sz1[0] != sz2[0] or sz1[1] != sz2[1]: 
                return True
        return False
    
    def _create_anchors(self, sizes:Sizes, device:torch.device):
        # AB: example anchors = torch.tensor with example size ([3069, 4]) 
        # AB: (4 coordinates, centre and size)
        self.sizes = sizes        
        self.anchors = create_anchors(sizes, self.ratios, self.scales).to(device)
    
    def _unpad(self, bbox_tgt, clas_tgt):
        # AB: returns target bbox and class for non-zero (non-background)
        """AB: input is (bb_tgt, clas_tgt),
           i is the first non-zero number in clas_tgt,
           pad_idx is initilized with 0,
           clas_tgt example: tensor([0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 3, 3]),
           torch.nonzero() returns indexes of nonzero numbers,
           AB added try for original formulation and except for returning simpy
           the highest index. Error occurs if all values of clas_tgt are zero.
           Update: error only occured in CPU mode... strange!
           """
        try:
          i = torch.min(torch.nonzero(clas_tgt-self.pad_idx))
        except:
          i = clas_tgt.shape[0]-1
          # AB: printing is inserted for debugging... only printed in CPU mode...
          print('\nclas_tgt.shape[0]', clas_tgt.shape[0]-1)
          print('i', i, '\n')
        return tlbr2cthw(bbox_tgt[i:]), clas_tgt[i:]-1+self.pad_idx
    
    def _focal_loss(self, clas_pred, clas_tgt):
        # AB only for classes
        encoded_tgt = encode_class(clas_tgt, clas_pred.size(1)) # one-hot encode
        # AB: .detach() returns a new Tensor, detached from the current backprob graph
        ps = torch.sigmoid(clas_pred.detach())
        weights = encoded_tgt * (1-ps) + (1-encoded_tgt) * ps
        alphas = (1-encoded_tgt) * self.alpha + encoded_tgt * (1-self.alpha)
        weights.pow_(self.gamma).mul_(alphas)
        clas_loss = F.binary_cross_entropy_with_logits(clas_pred, encoded_tgt, weights, reduction='sum')
        return clas_loss
        
    def _one_loss(self, clas_pred, bbox_pred, clas_tgt, bbox_tgt):
        # AB: add bbox loss
        # AB: before unpad: clas_tgt example: tensor([0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 3, 3])
        # AB: after  unpad: clas_tgt example: tensor([3, 3, 3])
        bbox_tgt, clas_tgt = self._unpad(bbox_tgt, clas_tgt)
        # AB: match_anchors example output: tensor([ 1,  1, -1, -1,  1,  1,  2,  2, -1, -1,  2,  2])
        # AB: -1 means background (IoU < 0.4) and the rest (IoU > 0.5) is matched to the target_bboxes
        # AB: again: matched to the target bbox ID not to the class!!
        matches = match_anchors(self.anchors, bbox_tgt)
        # AB: only take those bboxes whose match is not background (IoU bigger than 0.5)
        # AB: example: bbox_mask = tensor([True, True, False, False, True, ...])
        bbox_mask = matches>=0
        if bbox_mask.sum() != 0:
            # AB: bbox_pred updated to only those boxes which contain an object
            bbox_pred = bbox_pred[bbox_mask]
            # AB: bbox_tgt  updated to only those boxes which contain an object and match bbox_tgt in IoU
            # AB: again: bbox_tgt then only has some box IDs left
            # AB: (maybe also multiple times the same target box, if that was best fit to multiple anchors)
            bbox_tgt = bbox_tgt[matches[bbox_mask]]
            # AB: regression los between upd. bbox_pred and classes of target bboxes
            # AB: Creates a criterion that uses a squared term if the absolute
            # AB: element-wise error falls below 1 and an L1 term otherwise.
            # AB: It is less sensitive to outliers than the `MSELoss` and in some cases
            # AB: prevents exploding gradients (e.g. see `Fast R-CNN` paper by Ross Girshick).
            # AB: Also known as the Huber loss. 
            # AB: https://pytorch.org/docs/stable/_modules/torch/nn/modules/loss.html
            bb_loss = self.reg_loss(bbox_pred, bbox_to_activ(bbox_tgt, self.anchors[bbox_mask]))
        # AB: if no match between anchors and target, loss is 0
        else: bb_loss = 0.
        
        # AB: classification loss
        # AB: add_ is in-place version of add()
        # AB: matches could then be:   tensor([ 2, 2, 0, 0, 2, 2, 3, 3, 0, 0, 3, 3])
        # AB: clas_tgt could then be:  tensor([4, 4, 4])
        # AB: clas_mask could then be: tensor([ 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]) 
        matches.add_(1)
        clas_tgt = clas_tgt + 1
        clas_mask = matches>=0
        
        # AB: clas_pred is now on all spots in the vector
        clas_pred = clas_pred[clas_mask]
        # AB: a 0 spot is appended to the beginning of clas_tgt so that background gets matched to 0 later
        # AB: clas_tgt could then be:  tensor([ 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 4, 4, 4])
        clas_tgt = torch.cat([clas_tgt.new_zeros(1).long(), clas_tgt])
        # AB: clas_tgt updated to 0 to background, 
        clas_tgt = clas_tgt[matches[clas_mask]]
        
        # AB: reg_loss of misspositioned if is_object=True bbox 
        # AB: + class_loss divided by number of evaluated boxes
        return bb_loss + self._focal_loss(clas_pred, clas_tgt)/torch.clamp(bbox_mask.sum(), min=1.)
    
    def forward(self, output, bbox_tgts, clas_tgts):
        # AB: retrieve output
        clas_preds, bbox_preds, sizes = output
        if self._change_anchors(sizes): self._create_anchors(sizes, clas_preds.device)
        n_classes = clas_preds.size(2)
        
        # AB: for all predictions
        return sum([self._one_loss(cp, bp, ct, bt)
                    for (cp, bp, ct, bt) in zip(clas_preds, bbox_preds, clas_tgts, bbox_tgts)])/clas_tgts.size(0)

class SigmaL1SmoothLoss(nn.Module):

    def forward(self, output, target):
        reg_diff = torch.abs(target - output)
        # AB: squared of below threshold... further investigation necessary...
        reg_loss = torch.where(torch.le(reg_diff, 1/9), 4.5 * torch.pow(reg_diff, 2), reg_diff - 1/18)
        return reg_loss.mean()

def retina_net_split(model):
    groups = [list(model.encoder.children())[:6], list(model.encoder.children())[6:]]
    return groups + [list(model.children())[1:]]

def unpad(tgt_bbox, tgt_clas, pad_idx=0):
  """AB added try and except for nonzero function
     similar function to unpad inside model"""
  try:
    i = torch.min(torch.nonzero(tgt_clas-pad_idx))
  except:
    i = tgt_clas.shape[0]-1
  return tlbr2cthw(tgt_bbox[i:]), tgt_clas[i:]-1+pad_idx

#def process_output(output, i, detect_thresh=0.25):
#    """Process `output[i]` and return the predicted bboxes above `detect_thresh`."""
#    clas_pred, bbox_pred, sizes = output[0][i], output[1][i], output[2]
#    anchors = create_anchors(sizes, ratios, scales).to(clas_pred.device)
#    bbox_pred = activ_to_bbox(bbox_pred, anchors)
#    clas_pred = torch.sigmoid(clas_pred)
#    detect_mask = clas_pred.max(1)[0] > detect_thresh
#    bbox_pred, clas_pred = bbox_pred[detect_mask], clas_pred[detect_mask]
#    bbox_pred = tlbr2cthw(torch.clamp(cthw2tlbr(bbox_pred), min=-1, max=1))    
#    scores, preds = clas_pred.max(1)
#    return bbox_pred, scores, preds

def _draw_outline(o:Patch, lw:int):
    "Outline bounding box onto image `Patch`."
    o.set_path_effects([patheffects.Stroke(
        linewidth=lw, foreground='black'), patheffects.Normal()])

def draw_rect(ax:plt.Axes, b:Collection[int], color:str='white', text=None, text_size=14):
    "Draw bounding box on `ax`."
    patch = ax.add_patch(patches.Rectangle(b[:2], *b[-2:], fill=False, edgecolor=color, lw=2))
    _draw_outline(patch, 4)
    if text is not None:
        patch = ax.text(*b[:2], text, verticalalignment='top', color=color, fontsize=text_size, weight='bold')
        _draw_outline(patch,1)

#def show_preds(img, output, idx, detect_thresh=0.25, classes=None):
#    bbox_pred, scores, preds = process_output(output, idx, detect_thresh)
#    bbox_pred, preds, scores = bbox_pred.cpu(), preds.cpu(), scores.cpu()
#    t_sz = torch.Tensor([*img.size])[None].float()
#    bbox_pred[:,:2] = bbox_pred[:,:2] - bbox_pred[:,2:]/2
#    bbox_pred[:,:2] = (bbox_pred[:,:2] + 1) * t_sz/2
#    bbox_pred[:,2:] = bbox_pred[:,2:] * t_sz
#    bbox_pred = bbox_pred.long()
#    _, ax = plt.subplots(1,1)
#    for bbox, c, scr in zip(bbox_pred, preds, scores):
#        img.show(ax=ax)
#        txt = str(c.item()) if classes is None else classes[c.item()+1]
#        draw_rect(ax, [bbox[1],bbox[0],bbox[3],bbox[2]], text=f'{txt} {scr:.2f}')

def nms(boxes, scores, thresh=0.3):
    idx_sort = scores.argsort(descending=True)
    boxes, scores = boxes[idx_sort], scores[idx_sort]
    to_keep, indexes = [], torch.LongTensor(range_of(scores))
    while len(scores) > 0:
        to_keep.append(idx_sort[indexes[0]])
        iou_vals = IoU_values(boxes, boxes[:1]).squeeze()
        mask_keep = iou_vals < thresh
        if len(mask_keep.nonzero()) == 0: break
        boxes, scores, indexes = boxes[mask_keep], scores[mask_keep], indexes[mask_keep]
    return LongTensor(to_keep)

def process_output(output, i, detect_thresh=0.25):
    clas_pred,bbox_pred,sizes = output[0][i], output[1][i], output[2]
    anchors = create_anchors(sizes, ratios, scales).to(clas_pred.device)
    bbox_pred = activ_to_bbox(bbox_pred, anchors)
    clas_pred = torch.sigmoid(clas_pred)
    detect_mask = clas_pred.max(1)[0] > detect_thresh
    bbox_pred, clas_pred = bbox_pred[detect_mask], clas_pred[detect_mask]
    bbox_pred = tlbr2cthw(torch.clamp(cthw2tlbr(bbox_pred), min=-1, max=1))    
    if clas_pred.numel() == 0: return [],[],[]
    scores, preds = clas_pred.max(1)
    return bbox_pred, scores, preds

def show_preds(img, output, idx, detect_thresh=0.25, classes=None, ax=None):
    bbox_pred, scores, preds = process_output(output, idx, detect_thresh)
    if len(scores) != 0:
        to_keep = nms(bbox_pred, scores)
        bbox_pred, preds, scores = bbox_pred[to_keep].cpu(), preds[to_keep].cpu(), scores[to_keep].cpu()
        t_sz = torch.Tensor([*img.size])[None].float()
        bbox_pred[:,:2] = bbox_pred[:,:2] - bbox_pred[:,2:]/2
        bbox_pred[:,:2] = (bbox_pred[:,:2] + 1) * t_sz/2
        bbox_pred[:,2:] = bbox_pred[:,2:] * t_sz
        bbox_pred = bbox_pred.long()
    if ax is None: _, ax = plt.subplots(1,1)
    img.show(ax=ax)
    for bbox, c, scr in zip(bbox_pred, preds, scores):
        txt = str(c.item()) if classes is None else classes[c.item()+1]
        draw_rect(ax, [bbox[1],bbox[0],bbox[3],bbox[2]], text=f'{txt} {scr:.2f}')

def show_results(learn, start=0, n=5, detect_thresh=0.35, figsize=(10,25)):
    x,y = learn.data.one_batch(DatasetType.Valid, cpu=False)
    with torch.no_grad():
        z = learn.model.eval()(x)
    _,axs = plt.subplots(n, 2, figsize=figsize)
    for i in range(n):
        img,bbox = learn.data.valid_ds[start+i]
        img.show(ax=axs[i,0], y=bbox)
        show_preds(img, z, start+i, detect_thresh=detect_thresh, classes=learn.data.classes, ax=axs[i,1])

def get_predictions(output, idx, detect_thresh=0.05):
    bbox_pred, scores, preds = process_output(output, idx, detect_thresh)
    if len(scores) == 0: return [],[],[]
    to_keep = nms(bbox_pred, scores)
    return bbox_pred[to_keep], preds[to_keep], scores[to_keep]

def compute_ap(precision, recall):
    "Compute the average precision for `precision` and `recall` curve."
    recall = np.concatenate(([0.], list(recall), [1.]))
    precision = np.concatenate(([0.], list(precision), [0.]))
    for i in range(len(precision) - 1, 0, -1):
        precision[i - 1] = np.maximum(precision[i - 1], precision[i])
    idx = np.where(recall[1:] != recall[:-1])[0]
    ap = np.sum((recall[idx + 1] - recall[idx]) * precision[idx + 1])
    return ap

def compute_class_AP(model, dl, n_classes, iou_thresh=0.5, detect_thresh=0.35, num_keep=100):
    tps, clas, p_scores = [], [], []
    classes, n_gts = LongTensor(range(n_classes)),torch.zeros(n_classes).long()
    with torch.no_grad():
        for input,target in progress_bar(dl):
            output = model(input)
            for i in range(target[0].size(0)):
                bbox_pred, preds, scores = get_predictions(output, i, detect_thresh)
                tgt_bbox, tgt_clas = unpad(target[0][i], target[1][i])
                if len(bbox_pred) != 0 and len(tgt_bbox) != 0:
                    ious = IoU_values(bbox_pred, tgt_bbox)
                    max_iou, matches = ious.max(1)
                    detected = []
                    for i in range_of(preds):
                        if max_iou[i] >= iou_thresh and matches[i] not in detected and tgt_clas[matches[i]] == preds[i]:
                            detected.append(matches[i])
                            tps.append(1)
                        else: tps.append(0)
                    clas.append(preds.cpu())
                    p_scores.append(scores.cpu())
                n_gts += (tgt_clas.cpu()[:,None] == classes[None,:]).sum(0)
    tps, p_scores, clas = torch.tensor(tps), torch.cat(p_scores,0), torch.cat(clas,0)
    fps = 1-tps
    idx = p_scores.argsort(descending=True)
    tps, fps, clas = tps[idx], fps[idx], clas[idx]
    aps = []
    #return tps, clas
    for cls in range(n_classes):
        tps_cls, fps_cls = tps[clas==cls].float().cumsum(0), fps[clas==cls].float().cumsum(0)
        if tps_cls.numel() != 0 and tps_cls[-1] != 0:
            precision = tps_cls / (tps_cls + fps_cls + 1e-8)
            recall = tps_cls / (n_gts[cls] + 1e-8)
            aps.append(compute_ap(precision, recall))
        else: aps.append(0.)
    return aps

