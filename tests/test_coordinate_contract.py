"""坐标合同的跨组件同源测试，包括细长图、奇数舍入、裁剪和padding往返。"""
import unittest
from core.coordinate_contract import ImageTransform

class CoordinateTests(unittest.TestCase):
    def test_roundtrip_crop_letterbox(self):
        for h,w in [(241,319),(17,1023),(1023,17),(640,640)]:
            mapping=ImageTransform.letterbox(h,w,(640,640)).with_crop((7,11),(h+30,w+30))
            for x,y in [(7,11),(7+w/2,11+h/2),(7+w,11+h)]:
                back=mapping.to_original(*mapping.to_model(x,y))
                self.assertAlmostEqual(back[0],x,places=8)
                self.assertAlmostEqual(back[1],y,places=8)

    def test_legacy_rect_padding(self):
        mapping=ImageTransform.letterbox(240,320,(640,640),32)
        self.assertEqual(mapping.input_hw,(480,640))
        self.assertEqual(mapping.pad_ltrb,(0,0,0,0))

    def test_bad_mapping_rejected(self):
        with self.assertRaises(ValueError):
            ImageTransform(original_hw=(10,10),crop_xyxy=(0,0,12,10),resized_hw=(10,10),input_hw=(10,10),pad_ltrb=(0,0,0,0))
