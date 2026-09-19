"""创建/复用一个明确标识的微型合成项目，供真实页面和训练入口验收。"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from fastapi.testclient import TestClient
from core.paths import DATA_ROOT
from web.app_factory import create_app


def main():
    """只允许V2.4数据根；重复运行复用项目，不重复生成素材和数据目录。"""
    if "action_detection_v24" not in DATA_ROOT.parts:
        raise RuntimeError("合成验收仅允许V2.4工作区")
    with TestClient(create_app()) as client:
        name = "V2.4合成验收（非客户精度）"
        projects = client.get("/api/projects").json()
        found = next((p for p in projects if p["name"] == name), None)
        if found:
            print(found["id"])
            return
        response = client.post("/api/labels",json={"code":"A240","name":"合成细条","enabled":True})
        response.raise_for_status()
        response = client.post("/api/projects",json={"name":name,"label_codes":["A240"],"notes":"仅验证软件数据流，不能作为客户准确率证据"})
        response.raise_for_status(); project=response.json()
        source=DATA_ROOT/"assets"/"v24-synthetic.mp4"
        writer=cv2.VideoWriter(str(source),cv2.VideoWriter_fourcc(*"mp4v"),4,(320,240))
        if not writer.isOpened(): raise RuntimeError("合成录像编码器不可用")
        for index in range(8):
            frame=np.full((240,320,3),45,np.uint8)
            cv2.rectangle(frame,(30,30),(290,210),(85,85,85),-1)
            cv2.rectangle(frame,(80+index*3,50),(90+index*3,190),(225,225,225),-1)
            cv2.rectangle(frame,(220,50),(230,190),(225,225,225),-1)
            cv2.putText(frame,"SYNTHETIC",(10,225),cv2.FONT_HERSHEY_SIMPLEX,.5,(180,180,180),1)
            writer.write(frame)
        writer.release()
        with source.open("rb") as stream:
            response=client.post("/api/videos/upload",data={"project_id":project["id"]},files={"file":("v24-synthetic.mp4",stream,"video/mp4")})
        response.raise_for_status()
        response=client.post("/api/frame-sets/extract",json={"video_id":response.json()["id"],"sample_every_n_frames":1,"max_frames":4,"name":"合成双细条"})
        response.raise_for_status()
        print(project["id"])


if __name__ == "__main__": main()
