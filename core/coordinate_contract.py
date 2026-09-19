"""原图/裁剪/缩放/填充的显式坐标合同，独立于模型与GPU依赖。"""
from __future__ import annotations
from pydantic import BaseModel, ConfigDict, model_validator

class ImageTransform(BaseModel):
    """保存整数缩放尺寸与填充，往返映射不使用猜测的统一比例。"""
    model_config = ConfigDict(extra="forbid")
    original_hw: tuple[int,int]
    crop_xyxy: tuple[int,int,int,int]
    resized_hw: tuple[int,int]
    input_hw: tuple[int,int]
    pad_ltrb: tuple[int,int,int,int]

    @model_validator(mode="after")
    def check_bounds(self):
        h,w=self.original_hw
        x0,y0,x1,y1=self.crop_xyxy
        rh,rw=self.resized_hw
        ih,iw=self.input_hw
        l,t,r,b=self.pad_ltrb
        if min(h,w,rh,rw,ih,iw)<=0 or min(l,t,r,b)<0 or not (0<=x0<x1<=w and 0<=y0<y1<=h):
            raise ValueError("图像变换尺寸或裁剪边界无效")
        if rw+l+r!=iw or rh+t+b!=ih:
            raise ValueError("缩放与填充尺寸不等于模型输入")
        return self

    @classmethod
    def letterbox(cls, height:int, width:int, input_hw:tuple[int,int], auto_stride:int|None=None):
        """与YOLO rect=False的居中LetterBox整数舍入一致。"""
        ih,iw=input_hw
        ratio=min(ih/height,iw/width)
        rh,rw=round(height*ratio),round(width*ratio)
        dw,dh=iw-rw,ih-rh
        if auto_stride is not None:
            dw,dh=dw%auto_stride,dh%auto_stride
            ih,iw=rh+dh,rw+dw
        l,t=round(dw/2-.1),round(dh/2-.1)
        return cls(original_hw=(height,width),crop_xyxy=(0,0,width,height),resized_hw=(rh,rw),input_hw=(ih,iw),pad_ltrb=(l,t,dw-l,dh-t))

    def to_model(self, x:float, y:float) -> tuple[float,float]:
        """原图坐标进入模型输入；用于测试/证据坐标解释。"""
        x0,y0,x1,y1=self.crop_xyxy
        return ((x-x0)*self.resized_hw[1]/(x1-x0)+self.pad_ltrb[0],(y-y0)*self.resized_hw[0]/(y1-y0)+self.pad_ltrb[1])

    def to_original(self, x:float, y:float) -> tuple[float,float]:
        """模型输入坐标还原原图，不裁掉范围外坐标以掩盖错误。"""
        x0,y0,x1,y1=self.crop_xyxy
        return ((x-self.pad_ltrb[0])*(x1-x0)/self.resized_hw[1]+x0,(y-self.pad_ltrb[1])*(y1-y0)/self.resized_hw[0]+y0)

    def with_crop(self, offset:tuple[int,int], original_hw:tuple[int,int]):
        """模型处理了裁剪图时，保留既有缩放/填充并补齐原图坐标。"""
        x,y=offset
        return type(self)(**{**self.model_dump(),"original_hw":original_hw,"crop_xyxy":(x,y,x+self.original_hw[1],y+self.original_hw[0])})
