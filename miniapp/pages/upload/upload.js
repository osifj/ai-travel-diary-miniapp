// pages/upload/upload.js — 照片选择与上传
const app = getApp();
const { uploadFile } = require('../../utils/request');

Page({
  data: {
    selectedImages: [],     // 本地已选图片 [{path, size, ...}]
    uploadResults: [],      // 上传结果 [{photo_id, filename, exif}]
    isUploading: false,
    uploadProgress: 0,
    totalCount: 0,
    doneCount: 0,
    canAnalyze: false,
  },

  // 选择照片 (从相册)
  chooseImages() {
    const that = this;
    const remain = 20 - that.data.selectedImages.length;

    if (remain <= 0) {
      wx.showToast({ title: '最多选择 20 张照片', icon: 'none' });
      return;
    }

    wx.chooseMedia({
      count: remain,
      mediaType: ['image'],
      sourceType: ['album'],
      sizeType: ['original'],  // 尽量选择原图
      success(res) {
        const newImages = res.tempFiles.map(file => ({
          path: file.tempFilePath,
          size: file.size,
          name: `photo_${Date.now()}`,
        }));

        that.setData({
          selectedImages: [...that.data.selectedImages, ...newImages],
        });
      },
      fail(err) {
        console.error('选择照片失败:', err);
        if (err.errMsg.indexOf('cancel') === -1) {
          wx.showToast({ title: '选择照片失败', icon: 'none' });
        }
      },
    });
  },

  // 移除已选照片
  removeImage(e) {
    const index = e.currentTarget.dataset.index;
    const images = this.data.selectedImages;
    images.splice(index, 1);
    this.setData({ selectedImages: images });
  },

  // 上传全部已选照片
  async uploadAll() {
    if (this.data.selectedImages.length === 0) {
      wx.showToast({ title: '请先选择照片', icon: 'none' });
      return;
    }

    this.setData({
      isUploading: true,
      uploadProgress: 0,
      totalCount: this.data.selectedImages.length,
      doneCount: 0,
      uploadResults: [],
    });

    const results = [];
    const that = this;

    for (let i = 0; i < this.data.selectedImages.length; i++) {
      const image = this.data.selectedImages[i];

      try {
        wx.showLoading({ title: `上传中 ${i + 1}/${that.data.totalCount}` });

        const result = await uploadFile(image.path);
        results.push(result);

        that.setData({
          doneCount: i + 1,
          uploadProgress: Math.round(((i + 1) / that.data.totalCount) * 100),
          uploadResults: [...results],
        });

        wx.hideLoading();
      } catch (err) {
        wx.hideLoading();
        console.error('上传失败:', err);
        results.push({
          success: false,
          filename: image.name || 'unknown',
          error: err.message,
        });
        that.setData({
          doneCount: i + 1,
          uploadProgress: Math.round(((i + 1) / that.data.totalCount) * 100),
          uploadResults: [...results],
        });
      }
    }

    // 收集成功的 photo_ids
    const photoIds = results
      .filter(r => r.success && r.photo_id)
      .map(r => r.photo_id);

    app.globalData.uploadedPhotoIds = photoIds;

    this.setData({
      isUploading: false,
      canAnalyze: photoIds.length > 0,
    });

    if (photoIds.length > 0) {
      wx.showToast({
        title: `成功上传 ${photoIds.length} 张`,
        icon: 'success',
      });
    } else if (results.length > 0) {
      wx.showToast({ title: '上传失败，请重试', icon: 'none' });
    }
  },

  // 跳转到分析页
  goToAnalyze() {
    if (!this.data.canAnalyze) return;
    wx.navigateTo({ url: '/pages/analyzing/analyzing' });
  },
});
