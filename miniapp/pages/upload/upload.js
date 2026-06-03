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
    selectedCount: 0,
    hasSelectedImages: false,
    chooseButtonText: '从相册选择照片',
    showUploadButton: false,
    uploadButtonText: '上传 0 张照片',
    showUploadResults: false,
    isEmpty: true,
    progressText: '0 / 0 (0%)',
    travelDate: '',
    travelTime: '',
    hasTravelDate: false,
    hasTravelTime: false,
    dateText: '未选择日期',
    timeText: '未选择时间',
    locationName: '',
    locationAddress: '',
    locationLatitude: null,
    locationLongitude: null,
    hasLocation: false,
    locationText: '未选择地点',
    locationDetailText: '',
    metadataTip: '可选：如果微信临时文件丢失 EXIF，会用这里的日期/地点兜底。',
  },

  formatSize(size) {
    if (!size) return '';
    if (size > 1024 * 1024) {
      return `${(size / 1024 / 1024).toFixed(1)}MB`;
    }
    return `${(size / 1024).toFixed(0)}KB`;
  },

  createImageItem(file) {
    const path = file.tempFilePath || '';
    const extMatch = path.split('?')[0].match(/\.([a-zA-Z0-9]+)$/);
    const fileTypeText = extMatch ? extMatch[1].toUpperCase() : 'IMAGE';
    return {
      path: path,
      size: file.size,
      name: `photo_${Date.now()}`,
      hasSize: !!file.size,
      sizeText: this.formatSize(file.size),
      fileTypeText,
    };
  },

  createResultItem(result) {
    const exif = result.exif || null;
    const takenTime = exif && exif.taken_time ? exif.taken_time : '无时间';
    const hasGps = !!(exif && exif.has_gps);
    const gpsText = hasGps ? '有GPS' : '无GPS';
    const timeSourceText = this.formatSource(exif && exif.time_source);
    const locationSourceText = this.formatSource(exif && exif.location_source);
    const imageFormat = exif && exif.image_format ? exif.image_format : '';
    const exifText = `${takenTime} (${timeSourceText}) | ${gpsText} (${locationSourceText})`;

    return Object.assign({}, result, {
      icon: result.success ? '✅' : '❌',
      filenameText: result.filename || '未知文件',
      hasExif: !!exif,
      exifText,
      hasImageFormat: !!imageFormat,
      imageFormat,
      hasMissingMeta: !!(result.success && (!exif || !exif.taken_time || !hasGps)),
      hasError: !!result.error,
    });
  },

  formatSource(source) {
    const map = {
      exif: 'EXIF',
      user: '用户填写',
      ai: 'AI推测',
      unknown: '未知',
    };
    return map[source] || '未知';
  },

  setUploadData(changes) {
    const nextData = Object.assign({}, this.data, changes);
    const selectedCount = nextData.selectedImages.length;
    const resultCount = nextData.uploadResults.length;
    const hasTravelDate = !!nextData.travelDate;
    const hasTravelTime = !!nextData.travelTime;
    const hasLocation = !!(nextData.locationLatitude !== null && nextData.locationLongitude !== null);
    const locationText = hasLocation ? (nextData.locationName || '已选择地点') : '未选择地点';
    const locationDetailText = hasLocation ? (nextData.locationAddress || `${nextData.locationLatitude}, ${nextData.locationLongitude}`) : '';
    const derived = {
      selectedCount,
      hasSelectedImages: selectedCount > 0,
      chooseButtonText: selectedCount > 0 ? '继续添加照片' : '从相册选择照片',
      showUploadButton: selectedCount > 0 && !nextData.isUploading,
      uploadButtonText: `上传 ${selectedCount} 张照片`,
      showUploadResults: resultCount > 0 && !nextData.isUploading,
      isEmpty: selectedCount === 0 && resultCount === 0,
      progressText: `${nextData.doneCount} / ${nextData.totalCount} (${nextData.uploadProgress}%)`,
      hasTravelDate,
      hasTravelTime,
      dateText: hasTravelDate ? nextData.travelDate : '未选择日期',
      timeText: hasTravelTime ? nextData.travelTime : '未选择时间',
      hasLocation,
      locationText,
      locationDetailText,
    };
    this.setData(Object.assign({}, changes, derived));
  },

  onDateChange(e) {
    this.setUploadData({ travelDate: e.detail.value });
  },

  onTimeChange(e) {
    this.setUploadData({ travelTime: e.detail.value });
  },

  chooseLocation() {
    const that = this;
    wx.chooseLocation({
      success(res) {
        that.setUploadData({
          locationName: res.name || '已选择地点',
          locationAddress: res.address || '',
          locationLatitude: res.latitude,
          locationLongitude: res.longitude,
        });
      },
      fail(err) {
        console.error('选择地点失败:', err);
        if (err.errMsg.indexOf('cancel') === -1) {
          wx.showToast({ title: '选择地点失败', icon: 'none' });
        }
      },
    });
  },

  clearLocation() {
    this.setUploadData({
      locationName: '',
      locationAddress: '',
      locationLatitude: null,
      locationLongitude: null,
    });
  },

  buildUploadFormData() {
    const formData = {};
    if (this.data.travelDate) {
      const time = this.data.travelTime || '00:00';
      formData.client_taken_time = `${this.data.travelDate} ${time}:00`;
    }
    if (this.data.hasLocation) {
      formData.client_latitude = String(this.data.locationLatitude);
      formData.client_longitude = String(this.data.locationLongitude);
      formData.client_place_name = this.data.locationName || '';
      formData.client_address = this.data.locationAddress || '';
    }
    return formData;
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
        const newImages = res.tempFiles.map(file => that.createImageItem(file));

        that.setUploadData({
          selectedImages: that.data.selectedImages.concat(newImages),
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
    const images = this.data.selectedImages.slice();
    images.splice(index, 1);
    this.setUploadData({ selectedImages: images });
  },

  // 上传全部已选照片
  async uploadAll() {
    if (this.data.selectedImages.length === 0) {
      wx.showToast({ title: '请先选择照片', icon: 'none' });
      return;
    }

    this.setUploadData({
      isUploading: true,
      uploadProgress: 0,
      totalCount: this.data.selectedImages.length,
      doneCount: 0,
      uploadResults: [],
    });

    const results = [];
    const that = this;
    let firstErrorMessage = '';

    for (let i = 0; i < this.data.selectedImages.length; i++) {
      const image = this.data.selectedImages[i];

      try {
        wx.showLoading({ title: `上传中 ${i + 1}/${that.data.totalCount}` });

        const result = await uploadFile(image.path, that.buildUploadFormData());
        results.push(that.createResultItem(result));

        that.setUploadData({
          doneCount: i + 1,
          uploadProgress: Math.round(((i + 1) / that.data.totalCount) * 100),
          uploadResults: results.slice(),
        });

        wx.hideLoading();
      } catch (err) {
        wx.hideLoading();
        console.error('上传失败:', err);
        if (!firstErrorMessage) {
          firstErrorMessage = err.message || err.errMsg || '上传失败';
        }
        results.push(that.createResultItem({
          success: false,
          filename: image.name || 'unknown',
          error: err.message || err.errMsg || '上传失败',
        }));
        that.setUploadData({
          doneCount: i + 1,
          uploadProgress: Math.round(((i + 1) / that.data.totalCount) * 100),
          uploadResults: results.slice(),
        });
      }
    }

    // 收集成功的 photo_ids
    const photoIds = results
      .filter(r => r.success && r.photo_id)
      .map(r => r.photo_id);

    app.globalData.uploadedPhotoIds = photoIds;

    this.setUploadData({
      isUploading: false,
      canAnalyze: photoIds.length > 0,
    });

    if (photoIds.length > 0) {
      wx.showToast({
        title: `成功上传 ${photoIds.length} 张`,
        icon: 'success',
      });
      this.showMetadataHelpIfNeeded(results);
    } else if (results.length > 0) {
      this.showUploadErrorHelp(firstErrorMessage);
    }
  },

  showMetadataHelpIfNeeded(results) {
    const missingMeta = results.some(item => item.hasMissingMeta);
    if (!missingMeta) return;

    wx.showModal({
      title: '照片元数据缺失',
      content: '微信临时文件未携带完整拍摄时间或 GPS。可在上传前选择旅行日期和地点，作为本次照片兜底信息。',
      showCancel: false,
    });
  },

  showUploadErrorHelp(message) {
    const text = message || '上传失败，请重试';
    if (text.indexOf('domain list') !== -1 || text.indexOf('合法域名') !== -1) {
      wx.showModal({
        title: '域名未放行',
        content: '请使用真机调试并勾选“不校验合法域名”，或把后端 HTTPS 域名加入 uploadFile 合法域名。',
        showCancel: false,
      });
      return;
    }

    if (text.indexOf('timeout') !== -1 || text.indexOf('fail') !== -1 || text.indexOf('ERR') !== -1) {
      wx.showModal({
        title: '网络不可达',
        content: '请确认手机和电脑在同一 Wi-Fi，后端监听 0.0.0.0:8000，baseUrl 使用电脑局域网 IP。',
        showCancel: false,
      });
      return;
    }

    wx.showToast({ title: '上传失败，请重试', icon: 'none' });
  },

  // 跳转到分析页
  goToAnalyze() {
    if (!this.data.canAnalyze) return;
    wx.navigateTo({ url: '/pages/analyzing/analyzing' });
  },
});
