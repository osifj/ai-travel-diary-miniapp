// pages/map/map.js — 地图打点页 (占位)
// 完整实现需要接入腾讯地图或高德地图 SDK

Page({
  data: {
    markers: [],
    hasLocation: false,
  },

  onLoad() {
    // TODO: 从已分析照片中收集 GPS 坐标
    // 展示在地图上
    this.setData({
      hasLocation: false,
    });
  },

  goBack() {
    wx.navigateBack();
  },
});
