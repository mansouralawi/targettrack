import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

def getpad(ten,minshape):
    sh=ten.shape
    if len(sh)==4:
        W,H=sh[2],sh[3]
        return minshape[0]*(W//minshape[0]+(W%minshape[0]!=0))-W,minshape[1]*(H//minshape[1]+(H%minshape[1]!=0))-H
    elif len(sh)==5:
        W,H,D=sh[2],sh[3],sh[4]
        return minshape[0]*(W//minshape[0]+(W%minshape[0]!=0))-W,minshape[1]*(H//minshape[1]+(H%minshape[1]!=0))-H,minshape[2]*(D//minshape[2]+(D%minshape[2]!=0))-D
    else:
        assert False, str(sh)+"not valid"

class ASPP3DConv(nn.Module):
    def __init__(self, in_channels, out_channels, dilation):
        super().__init__()
        self.conv=nn.Conv3d(in_channels, out_channels, 3, padding=dilation, dilation=dilation, bias=False)
        self.norm=nn.BatchNorm3d(out_channels)
        self.relu=nn.ReLU(inplace=True)

    def forward(self,x):
        return self.relu(self.norm(self.conv(x)))


class ASPP3D(nn.Module):
    def __init__(self, in_channels,out_channels, atrous_rates):
        super().__init__()
        self.relu=nn.ReLU(inplace=True)

        self.conv=nn.Conv3d(in_channels, out_channels, 1, bias=False)
        self.norm=nn.BatchNorm3d(out_channels)

        DilConvs = []
        for rate in atrous_rates:
            DilConvs.append(ASPP3DConv(in_channels, out_channels, rate))

        self.DilConvs = nn.ModuleList(DilConvs)

        self.compressionconv = nn.Conv3d((len(atrous_rates)+1) * out_channels, out_channels, 1, bias=False)
        self.compressionnorm=nn.BatchNorm3d(out_channels)

    def forward(self, x):
        res = []
        res.append(self.norm(self.conv(x)))
        for conv in self.DilConvs:
            res.append(conv(x))
        res = torch.cat(res, dim=1)
        return self.relu(self.compressionnorm(self.compressionconv(res)))

class ASPP2DConv(nn.Module):
    def __init__(self, in_channels, out_channels, dilation):
        super().__init__()
        self.conv=nn.Conv2d(in_channels, out_channels, 3, padding=dilation, dilation=dilation, bias=False)
        self.norm=nn.BatchNorm2d(out_channels)
        self.relu=nn.ReLU(inplace=True)

    def forward(self,x):
        return self.relu(self.norm(self.conv(x)))


class ASPP2D(nn.Module):
    def __init__(self, in_channels,out_channels, atrous_rates):
        super().__init__()
        self.relu=nn.ReLU(inplace=True)

        self.conv=nn.Conv2d(in_channels, out_channels, 1, bias=False)
        self.norm=nn.BatchNorm2d(out_channels)

        DilConvs = []
        for rate in atrous_rates:
            DilConvs.append(ASPP2DConv(in_channels, out_channels, rate))

        self.DilConvs = nn.ModuleList(DilConvs)

        self.compressionconv = nn.Conv2d((len(atrous_rates)+1) * out_channels, out_channels, 1, bias=False)
        self.compressionnorm=nn.BatchNorm2d(out_channels)

    def forward(self, x):
        res = []
        res.append(self.norm(self.conv(x)))
        for conv in self.DilConvs:
            res.append(conv(x))
        res = torch.cat(res, dim=1)
        return self.relu(self.compressionnorm(self.compressionconv(res)))


# Define your chunked_upsample function
def chunked_upsample(input_tensor, scale_factor, chunk_size=1, mode='nearest'):
    # chunk_size = input_tensor.size(0)
    # print("input_tensor.size(0)",input_tensor.size(0),input_tensor.size())
    # if chunk_size >= batch_size:
    #     return F.interpolate(input_tensor, scale_factor=scale_factor, mode=mode)

    chunks = torch.chunk(input_tensor, chunks=chunk_size, dim=0)
    upsampled_chunks = [F.interpolate(chunk, scale_factor=scale_factor, mode=mode) for chunk in chunks]
    output_tensor = torch.cat(upsampled_chunks, dim=0)

    return output_tensor

def chunked_interpolate(input_tensor, target_size, chunk_size=1, mode='nearest'):
    """
    Applies F.interpolate to the input tensor in chunks to avoid memory issues.
    
    Args:
        input_tensor (torch.Tensor): The input tensor to upsample.
        target_size (tuple): The target size to interpolate to (must match ori.shape[2:]).
        chunk_size (int): The number of chunks to split the tensor into along the batch dimension.
        mode (str): The upsampling algorithm to use ('nearest', 'bilinear', etc.).
    
    Returns:
        torch.Tensor: The upsampled tensor.
    """
    batch_size = input_tensor.size(0)

    # If batch size is smaller than chunk size, avoid chunking
    if chunk_size >= batch_size:
        return F.interpolate(input_tensor, size=target_size, mode=mode)

    # Split the input tensor into chunks along the batch dimension
    chunks = torch.chunk(input_tensor, chunks=chunk_size, dim=0)

    # Apply interpolation to each chunk
    upsampled_chunks = [F.interpolate(chunk, size=target_size, mode=mode) for chunk in chunks]

    # Concatenate the upsampled chunks back together along the batch dimension
    output_tensor = torch.cat(upsampled_chunks, dim=0)

    return output_tensor


class ThreeDCN(nn.Module):
    def __init__(self, n_channels=3,n_filt_init=16,growth=8,kernel_size=3,compress_targ=8,num_classes=10):
        super().__init__()

        self.relu=nn.ReLU(inplace=True)
        self.down=nn.MaxPool3d(kernel_size=2)
        self.down_noz=nn.MaxPool3d(kernel_size=(2,2,1))


        n_filt_in=n_channels
        n_filt=n_filt_init
        self.conv1=nn.Conv3d(n_filt_in, n_filt, kernel_size=5, stride=1,padding=2,bias=False)
        self.norm1=nn.BatchNorm3d(n_filt)
        self.conv2=nn.Conv3d(n_filt, n_filt, kernel_size=5, stride=1,padding=2,bias=False)
        self.norm2=nn.BatchNorm3d(n_filt)


        n_filt_in=n_filt
        n_filt+=growth
        self.conv3=nn.Conv3d(n_filt_in, n_filt, kernel_size=3, stride=1,padding=1,bias=False)
        self.norm3=nn.BatchNorm3d(n_filt)
        self.conv4=nn.Conv3d(n_filt, n_filt, kernel_size=3, stride=1,padding=1,bias=False)
        self.norm4=nn.BatchNorm3d(n_filt)
        self.up1=nn.Upsample(scale_factor=(1,2,2))

        #We skip one downsample in z for 2 down samples
        #two down samples are done, 64x40x8 for us
        n_filt_in=n_filt
        n_filt+=growth
        self.conv5=nn.Conv3d(n_filt_in, n_filt, kernel_size=3, stride=1,padding=1,bias=False)
        self.norm5=nn.BatchNorm3d(n_filt)
        self.conv6=nn.Conv3d(n_filt, n_filt, kernel_size=3, stride=1,padding=1,bias=False)
        self.norm6=nn.BatchNorm3d(n_filt)
        self.compression2conv=nn.Conv3d(n_filt, compress_targ, kernel_size=1, stride=1,bias=False)
        self.compression2norm=nn.BatchNorm3d(compress_targ)
        self.up2=nn.Upsample(scale_factor=(1,2,2))

        #still at same level 64x40x8
        n_filt_in=n_filt
        n_filt+=growth
        self.ASPP3D2=ASPP3D(n_filt_in,n_filt, atrous_rates=((3,3,1),(6,6,2),(9,9,3)))
        self.compressionASPP3D2conv=nn.Conv3d(n_filt, compress_targ, kernel_size=1, stride=1,bias=False)
        self.compressionASPP3D2norm=nn.BatchNorm3d(compress_targ)#compress to send up
        #we already have up2

        #continue going down, 32x20x4 for us
        n_filt_in=n_filt
        n_filt+=growth
        self.ASPP3D3=ASPP3D(n_filt_in,n_filt, atrous_rates=((3,3,1),(6,6,1),(9,9,2)))
        self.compressionASPP3D3conv=nn.Conv3d(n_filt, compress_targ, kernel_size=1, stride=1,bias=False)
        self.compressionASPP3D3norm=nn.BatchNorm3d(compress_targ)#compress to send up
        self.up3=nn.Upsample(scale_factor=(1,4,4))

        #continue going down, 16x10x4 for us no z
        n_filt_in=n_filt
        n_filt+=growth
        self.ASPP3D4=ASPP3D(n_filt_in,n_filt, atrous_rates=((2,2,1),(3,3,1),(4,4,2),(5,5,2)))
        self.compressionASPP3D4conv=nn.Conv3d(n_filt, compress_targ, kernel_size=1, stride=1,bias=False)
        self.compressionASPP3D4norm=nn.BatchNorm3d(compress_targ)#compress to send up
        self.up4=nn.Upsample(scale_factor=(1,8,8))

        self.conv_out=nn.Conv3d(n_channels+n_filt_init+(n_filt_init+growth)+4*compress_targ,num_classes, kernel_size=1, stride=1,bias=True)

        for name, param in self.named_parameters():
            if "conv" in name and 'weight' in name:
                n = param.size(0) * param.size(2) * param.size(3)* param.size(4)
                param.data.normal_().mul_(np.sqrt(2. / n))
                #print(name)
            elif "norm" in name and 'weight' in name:
                param.data.fill_(1)
                #print(name)
            elif "norm" in name and 'bias' in name:
                param.data.fill_(0)
                #print(name)
            else:
                pass
                #print("no init",name)

    def forward(self, x,verbose=False):
        padW,padH,padD=getpad(x,minshape=(32,32,4))
        x=nn.functional.pad(x, pad=(padD,0,padH,0,padW,0), mode='constant', value=0.0)
        
        ori=x#n_channels
        if verbose:
            print(x.size())
        x=self.relu(self.norm1(self.conv1(x)))
        x=self.relu(self.norm2(self.conv2(x)))
        send0=x #n_filt_init
        x=self.down(x)

        if verbose:
            print(x.size())
        x=self.relu(self.norm3(self.conv3(x)))
        x=self.relu(self.norm4(self.conv4(x)))
        # send1=self.up1(x) #n_filt_init+growth
        send1=chunked_upsample(x,2,16)
        x=self.down_noz(x)

        #remember we don't down 64x40x8
        if verbose:
            print(x.size())
        x=self.relu(self.norm5(self.conv5(x)))
        x=self.relu(self.norm6(self.conv6(x)))#48+32
        send2=chunked_upsample(self.relu(self.compression2norm(self.compression2conv(x))),(2,2,1),16) #64->save memory
        #compress_targ

        x=self.ASPP3D2(x)
        send2ASPP3D=chunked_upsample(self.relu(self.compressionASPP3D2norm(self.compressionASPP3D2conv(x))),(2,2,1),16)
        x=self.down(x)

        #remember we don't down z 32x20x4
        x=self.ASPP3D3(x)
        send3ASPP3D=chunked_upsample(self.relu(self.compressionASPP3D3norm(self.compressionASPP3D3conv(x))),(4,4,2),16)
        x=self.down_noz(x)

        #remember we don't down z 16x10x4
        x=self.ASPP3D4(x)
        send4ASPP3D=chunked_upsample(self.relu(self.compressionASPP3D4norm(self.compressionASPP3D4conv(x))),(8,8,2),16)

        #1+32+(32+32)+(32)+4*32
        torch.cuda.empty_cache()
        send1 = chunked_interpolate(send1, target_size=ori.shape[2:],chunk_size=4, mode='nearest')
        send2 = chunked_interpolate(send2, target_size=ori.shape[2:],chunk_size=4, mode='nearest')
        send2ASPP3D = chunked_interpolate(send2ASPP3D, target_size=ori.shape[2:],chunk_size=4, mode='nearest')
        send3ASPP3D = chunked_interpolate(send3ASPP3D, target_size=ori.shape[2:],chunk_size=4,mode='nearest')
        send4ASPP3D = chunked_interpolate(send4ASPP3D, target_size=ori.shape[2:],chunk_size=4,mode='nearest')
        # print(f"ori: {ori.size()}, send0: {send0.size()}, send1: {send1.size()}, send2: {send2.size()}, send2ASPP3D: {send2ASPP3D.size()}, send3ASPP3D: {send3ASPP3D.size()}, send4ASPP3D: {send4ASPP3D.size()}")
        x=torch.cat([ori,send0,send1,send2,send2ASPP3D,send3ASPP3D,send4ASPP3D],dim=1)#n_channel+32+64+32+32+32

        x=self.conv_out(x)

        return x[:,:,padW:,padH:,padD:]

class TwoDCN(nn.Module):
    def __init__(self, n_channels=3,n_filt_init=16,growth=24,kernel_size=3,compress_targ=32,num_classes=10):
        super().__init__()

        self.relu=nn.ReLU(inplace=True)
        self.down=nn.MaxPool2d(kernel_size=2)

        n_filt_in=n_channels
        n_filt=n_filt_init
        self.conv1=nn.Conv2d(n_filt_in, n_filt, kernel_size=5, stride=1,padding=2,bias=False)
        self.norm1=nn.BatchNorm2d(n_filt)
        self.conv2=nn.Conv2d(n_filt, n_filt, kernel_size=5, stride=1,padding=2,bias=False)
        self.norm2=nn.BatchNorm2d(n_filt)


        n_filt_in=n_filt
        n_filt+=growth
        self.conv3=nn.Conv2d(n_filt_in, n_filt, kernel_size=3, stride=1,padding=1,bias=False)
        self.norm3=nn.BatchNorm2d(n_filt)
        self.conv4=nn.Conv2d(n_filt, n_filt, kernel_size=3, stride=1,padding=1,bias=False)
        self.norm4=nn.BatchNorm2d(n_filt)
        self.up1=nn.Upsample(scale_factor=2)

        #We skip one downsample in z for 2 down samples
        #two down samples are done, 64x40x8 for us
        n_filt_in=n_filt
        n_filt+=growth
        self.conv5=nn.Conv2d(n_filt_in, n_filt, kernel_size=3, stride=1,padding=1,bias=False)
        self.norm5=nn.BatchNorm2d(n_filt)
        self.conv6=nn.Conv2d(n_filt, n_filt, kernel_size=3, stride=1,padding=1,bias=False)
        self.norm6=nn.BatchNorm2d(n_filt)
        self.compression2conv=nn.Conv2d(n_filt, compress_targ, kernel_size=1, stride=1,bias=False)
        self.compression2norm=nn.BatchNorm2d(compress_targ)
        self.up2=nn.Upsample(scale_factor=(4,4))

        #still at same level 64x40x8
        n_filt_in=n_filt
        n_filt+=growth
        self.ASPP2D2=ASPP2D(n_filt_in,n_filt, atrous_rates=((3,3),(6,6),(9,9)))
        self.compressionASPP2D2conv=nn.Conv2d(n_filt, compress_targ, kernel_size=1, stride=1,bias=False)
        self.compressionASPP2D2norm=nn.BatchNorm2d(compress_targ)#compress to send up
        #we already have up2

        #continue going down, 32x20x4 for us
        n_filt_in=n_filt
        n_filt+=growth
        self.ASPP2D3=ASPP2D(n_filt_in,n_filt, atrous_rates=((3,3),(6,6),(9,9)))
        self.compressionASPP2D3conv=nn.Conv2d(n_filt, compress_targ, kernel_size=1, stride=1,bias=False)
        self.compressionASPP2D3norm=nn.BatchNorm2d(compress_targ)#compress to send up
        self.up3=nn.Upsample(scale_factor=(8,8))

        #continue going down, 16x10x4 for us no z
        n_filt_in=n_filt
        n_filt+=growth
        self.ASPP2D4=ASPP2D(n_filt_in,n_filt, atrous_rates=((2,2),(3,3),(4,4),(5,5)))
        self.compressionASPP2D4conv=nn.Conv2d(n_filt, compress_targ, kernel_size=1, stride=1,bias=False)
        self.compressionASPP2D4norm=nn.BatchNorm2d(compress_targ)#compress to send up
        self.up4=nn.Upsample(scale_factor=(16,16))

        self.conv_out=nn.Conv2d(n_channels+n_filt_init+(n_filt_init+growth)+4*compress_targ,num_classes, kernel_size=1, stride=1,bias=True)

        for name, param in self.named_parameters():
            if "conv" in name and 'weight' in name:
                n = param.size(0) * param.size(2) * param.size(3)
                param.data.normal_().mul_(np.sqrt(2. / n))
                #print(name)
            elif "norm" in name and 'weight' in name:
                param.data.fill_(1)
                #print(name)
            elif "norm" in name and 'bias' in name:
                param.data.fill_(0)
                #print(name)
            else:
                pass
                #print("no init",name)

    def forward(self, x,verbose=False):
        padW,padH=getpad(x,minshape=(32,32))
        x=nn.functional.pad(x, pad=(padH,0,padW,0), mode='constant', value=0.0)
        
        ori=x#n_channels
        if verbose:
            print(x.size())
        x=self.relu(self.norm1(self.conv1(x)))
        x=self.relu(self.norm2(self.conv2(x)))
        send0=x #n_filt_init
        x=self.down(x)

        if verbose:
            print(x.size())
        x=self.relu(self.norm3(self.conv3(x)))
        x=self.relu(self.norm4(self.conv4(x)))
        send1=self.up1(x) #n_filt_init+growth
        x=self.down(x)

        if verbose:
            print(x.size())
        x=self.relu(self.norm5(self.conv5(x)))
        x=self.relu(self.norm6(self.conv6(x)))#48+32
        send2=self.up2(self.relu(self.compression2norm(self.compression2conv(x)))) #64->save memory
        #compress_targ

        x=self.ASPP2D2(x)
        send2ASPP3D=self.up2(self.relu(self.compressionASPP2D2norm(self.compressionASPP2D2conv(x))))
        x=self.down(x)

        x=self.ASPP2D3(x)
        send3ASPP3D=self.up3(self.relu(self.compressionASPP2D3norm(self.compressionASPP2D3conv(x))))
        x=self.down(x)

        x=self.ASPP2D4(x)
        send4ASPP3D=self.up4(self.relu(self.compressionASPP2D4norm(self.compressionASPP2D4conv(x))))

        #1+32+(32+32)+(32)+4*32
        x=torch.cat([ori,send0,send1,send2,send2ASPP3D,send3ASPP3D,send4ASPP3D],dim=1)#n_channel+32+64+32+32+32

        x=self.conv_out(x)

        return x[:,:,padW:,padH:]

class AutoEnc2d(nn.Module):
    def __init__(self,sh2d,n_channels=3,n_z=20,out=torch.sigmoid):
        super().__init__()
        x_mock=torch.randn(1,1,sh2d[0],sh2d[1])
        padW,padH=getpad(x_mock,minshape=(32,32))
        sh2d=np.array(sh2d)+np.array([padW,padH])
        self.relu=nn.ReLU(inplace=True)
        self.down=nn.MaxPool2d(kernel_size=2)

        dim_in=n_channels
        dim_out=16
        self.conv1=nn.Conv2d(dim_in, dim_out, kernel_size=3, stride=1,padding=1,bias=False)
        self.norm1=nn.BatchNorm2d(dim_out)

        dim_in=dim_out
        dim_out=32
        self.conv2=nn.Conv2d(dim_in, dim_out, kernel_size=3, stride=1,padding=1,bias=False)
        self.norm2=nn.BatchNorm2d(dim_out)

        dim_in=dim_out
        dim_out=48
        self.conv3=nn.Conv2d(dim_in, dim_out, kernel_size=3, stride=1,padding=1,bias=False)
        self.norm3=nn.BatchNorm2d(dim_out)

        dim_in=dim_out
        dim_out=64
        self.conv4=nn.Conv2d(dim_in, dim_out, kernel_size=3, stride=1,padding=1,bias=False)
        self.norm4=nn.BatchNorm2d(dim_out)

        dim_in=dim_out
        dim_out=80
        self.conv5=nn.Conv2d(dim_in, dim_out, kernel_size=3, stride=1,padding=1,bias=False)
        self.norm5=nn.BatchNorm2d(dim_out)

        dim_in=dim_out
        dim_out=96
        self.conv6=nn.Conv2d(dim_in, dim_out, kernel_size=3, stride=1,padding=1,bias=False)
        self.norm6=nn.BatchNorm2d(dim_out)

        self.latent_shape=((sh2d[0]//32),(sh2d[1]//32))
        self.lin_enc=nn.Linear(self.latent_shape[0]*self.latent_shape[1]*dim_out,n_z)
        self.lin_dec=nn.Linear(n_z,self.latent_shape[0]*self.latent_shape[1]*dim_out)

        dim_in=dim_out
        dim_out=80
        self.convt7=nn.ConvTranspose2d(dim_in, dim_out, kernel_size=2, stride=2,bias=False)
        self.conv7=nn.Conv2d(dim_out, dim_out, kernel_size=1, stride=1,bias=False)
        self.norm7=nn.BatchNorm2d(dim_out)

        dim_in=dim_out
        dim_out=64
        self.convt8=nn.ConvTranspose2d(dim_in, dim_out, kernel_size=2, stride=2,bias=False)
        self.conv8=nn.Conv2d(dim_out, dim_out, kernel_size=1, stride=1,bias=False)
        self.norm8=nn.BatchNorm2d(dim_out)

        dim_in=dim_out
        dim_out=48
        self.convt9=nn.ConvTranspose2d(dim_in, dim_out, kernel_size=2, stride=2,bias=False)
        self.conv9=nn.Conv2d(dim_out, dim_out, kernel_size=1, stride=1,bias=False)
        self.norm9=nn.BatchNorm2d(dim_out)

        dim_in=dim_out
        dim_out=32
        self.convt10=nn.ConvTranspose2d(dim_in, dim_out, kernel_size=2, stride=2,bias=False)
        self.conv10=nn.Conv2d(dim_out, dim_out, kernel_size=1, stride=1,bias=False)
        self.norm10=nn.BatchNorm2d(dim_out)

        dim_in=dim_out
        dim_out=16
        self.convt11=nn.ConvTranspose2d(dim_in, dim_out, kernel_size=2, stride=2,bias=False)
        self.conv11=nn.Conv2d(dim_out, dim_out, kernel_size=1, stride=1,bias=False)
        self.norm11=nn.BatchNorm2d(dim_out)

        self.conv_out=nn.Conv2d(dim_out,n_channels, kernel_size=3, stride=1,padding=1,bias=True)

        self.out=out

        for name, param in self.named_parameters():
            if "conv" in name and 'weight' in name:
                n = param.size(0) * param.size(2) * param.size(3)
                param.data.normal_().mul_(np.sqrt(2. / n))
            elif "norm" in name and 'weight' in name:
                param.data.fill_(1)
            elif "norm" in name and 'bias' in name:
                param.data.fill_(0)
            else:
                pass

    def forward(self, x):
        padW,padH=getpad(x,minshape=(32,32))
        x=nn.functional.pad(x, pad=(padH,0,padW,0), mode='constant', value=0.0)
        
        x=self.relu(self.norm1(self.conv1(x)))
        x=self.down(x)
        x=self.relu(self.norm2(self.conv2(x)))
        x=self.down(x)
        x=self.relu(self.norm3(self.conv3(x)))
        x=self.down(x)
        x=self.relu(self.norm4(self.conv4(x)))
        x=self.down(x)
        x=self.relu(self.norm5(self.conv5(x)))
        x=self.down(x)
        x=self.relu(self.norm6(self.conv6(x)))
        x=x.reshape(x.size(0),-1)
        latent=self.lin_enc(x)
        x=self.lin_dec(latent)
        x=x.reshape(x.size(0),96,self.latent_shape[0],self.latent_shape[1])
        x=self.relu(self.norm7(self.conv7(self.convt7(x))))
        x=self.relu(self.norm8(self.conv8(self.convt8(x))))
        x=self.relu(self.norm9(self.conv9(self.convt9(x))))
        x=self.relu(self.norm10(self.conv10(self.convt10(x))))
        x=self.relu(self.norm11(self.conv11(self.convt11(x))))
        res=self.out(self.conv_out(x))
        res=res[:,:,padW:,padH:]
        
        return res,latent
        
        
        