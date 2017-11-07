# coding=utf-8
# 导入蓝图
from . import api
# 导入数据库实例
from ihome import redis_store, constants, db
from flask import current_app, jsonify, request
# 导入模型类
from ihome.models import Area, House, Facility, HouseImage
# 导入自定义状态码
from ihome.utils.response_code import RET
# 导入json 模块
import json
# 导入登录验证装饰器
from ihome.utils.commons import login_required
from ihome.utils.image_storage import storage

@api.route('/areas', methods=['GET'])
def get_area_info():
    """
    获取区域信息
    1/尝试从redis中获取区域信息
    2/校验查询结果
    3/查询mysql数据库
    4/校验查询结果
    5/存储查询结果,[]来存储数据,包含城区基本信息
    6/序列化数据,把城区信息转换成json字符串,json.dumps
    7/返回结果
    :return:
    """
    # 尝试从redis获取城区信息,因为要保存返回数据,需要保存查询结果
    try:
        areas = redis_store.get("area_info")
    except Exception as e:
        current_app.logger.error(e)
        # 查询发生异常,把areas置为空
        areas = None
    # 校验查询结果
    if areas:
        # 记录访问区域信息的时间
        current_app.looger.info('hit area info redis')
        # redis 中存储的数据是json字符串,可以直接返回,不需要调用jsonify
        return '{"errno":0,"errmsg":"OK","data":%s}' % areas
    try:
        areas = Area.query.all()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg="查询区域信息异常")
    if not areas:
        return jsonify(errno=RET.DATAERR, errmsg="查询无数据")
    # 存储查询数据,遍历区域信息
    areas_list = []
    for area in areas:
        areas_list.append(area.to_dict())
        # 序列化数据转成json字符串
        areas_josn = json.dumps(areas_list)
        # 把区域信息存储到redis数据库
    try:
        redis_store.setex("area_info", constants.AREA_INFO_REDIS_EXPIRES,areas_josn)
    except Exception as e:
        current_app.logger.error(e)
        # return jsonify(errno=RET.DBERR, errmsg="保存数据库失败")
    # 返回json 数据
    return '{"errno":0,"errmsg":"OK","data":%s}' % areas_josn

@api.route('/houses', methods=['POST'])
@login_required
def save_house_info():
    """
    发布新房屋
    1/获取参数,g变量
    2/获取房屋发布的基本信息
    3/校验房屋基本信息的完整行
    4/价格单位进行处理,price = int(float(price)*100)
    5/保存房屋信息,house = House().title
    6/处理配套设施参数,判断配套设施的存在
    7/存储房屋数据,提交数据异常,需进行回滚
    8/返回结果 house_id

    :return:
    """
    # 获取用户id
    user_id = g.user_id
    # 获取房屋参数
    house_data = request.get_json()
    # 校验参数
    if not house_data:
        return jsonify(errno=RET.PARAMERR, errmsg="参数错误")
    # 获取房屋详细的参数信息
    title = house_data.get("title")
    price = house_data.get("price")
    area_id = house_data.get("area_id")
    address = house_data.get("address")
    room_count = house_data.get("room_count")
    acreage = house_data.get("acreage")  # 房间大小
    unit = house_data.get("unit")  # 房型
    capacity = house_data.get("capacity")  # 适住人数
    beds = house_data.get("beds")  # 卧床配置
    deposit = house_data.get("deposit")  # 押金
    min_days = house_data.get("min_days")  # 最小入住天数
    max_days = house_data.get("max_days")  # 最大入住天数
    # 校验参数完整性
    if not all([
        title,price,area_id,address,room_count,acreage,unit,capacity,beds,deposit,min_days,max_days
    ]):
        return jsonify(errno=RET.PARAMERR, errmsg="参数缺失")
    # 转换价格单位
    try:
        price = int(float(price)*100)
        deposit = int(float(deposit)*100)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DATAERR, errmsg="价格数据异常")
    # 准备存储房屋基本信息,构建模型类对象
    house = House()
    house.user_id = user_id
    house.area_id = area_id
    house.title = title
    house.price = price
    house.address = address
    house.room_count = room_count
    house.acreage = acreage
    house.unit = unit
    house.capacity = capacity
    house.beds = beds
    house.deposit = deposit
    house.min_days = min_days
    house.max_days = max_days
    # 尝试获取房屋配套设施数据
    facility = house_data.get("facility")
    # 校验房屋设施存在
    if facility:
        # 保存查询结果
        try:
            # 判断用户上传的设施编号,在数据库中存在
            facilities = Facility.query.filter(Facility.id.in_(facility)).all()
            # 保存过滤后的房屋设施信息
            house.facilities = facilities
        except Exception as e:
            current_app.logger.error(e)
            return jsonify(errno=RET.DBERR, errmsg="查询房屋设施信息异常")
    # 保存房屋数据到数据库
        try:
            db.session.add(house)
            db.session.commit()
        except Exception as e:
            current_app.logger.error(e)
            # 提交数据失败,进行回滚
            db.session.rollback()
            return jsonify(errno=RET.DBERR, errmsg="保存房屋信息失败")
        # 返回结果,房屋id
        return jsonify(errno=RET.OK,errmsg="OK", data={"bouse_id":house.id})

@api.route('/houses/<int:house_id>/images', methods=['POST'])
@login_required
def save_house_image(house_id):
    """
    保存房屋图片
    1/获取参数,house_image,校验房屋图片存在
    2/获取参数,确认房屋存在,查询数据库,校验数据结果
    3/ 读取图片数据
    4/ 调用七牛云,获取图片名称
    5/ 保存房屋图片信息,HouseImage(),House(),判断房屋主图片是否设置
    6/拼接图片的url
    7/返回结果
    :param house_id:
    :return:
    """
    # 获取图片参数
    image = request.files.get("house_iamge")
    # 校验参数
    if not image:
        return jsonify(errno=RET.PARAMERR,errmsg="图片未上传")
    # 校验房屋存在
    try:
         house = House.query.filter_by(id=house_id).first()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg="房屋查询异常")
    # 校验产讯结果
    if not house:
        return jsonify(errno=RET.NODATA,errmsg="房屋不存在")
    # 读取图片信息
    image_data = image.read()
    # 调用七牛云接口
    try:
        image_name = storage(image_data)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.THIRDERR,errmsg="上传七牛元图片失败")
    # 保存房屋图片到houseIMage()
    house_image = HouseImage()
    house_image.house_id = house_id
    house_image.url = image_name
    # 提交房屋图盘名称到数据库回话对象
    db.session.add(house_image)
    #




