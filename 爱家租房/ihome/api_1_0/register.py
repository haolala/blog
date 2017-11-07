# -*- coding:utf-8 -*-
# 导入云通信接口
from ihome.utils import sms
# 导入图片验证码扩展
from ihome.utils.captcha.captcha import captcha
# 导入redis数据库实例
from ihome import redis_store,constants,db
# 导入flask内置的模块
from flask import current_app,jsonify,make_response,request,session
# 导入自定义状态码
from ihome.utils.response_code import RET
# 导入数据库模型类User
from ihome.models import User
# 导入蓝图对象
from . import api
# 导入正则模块,用来校验手机号格式
import re
# 导入random模块,生成短信验证码
import random

@api.route('/imagecode/<image_code_id>',methods=['GET'])
def generate_image_code(image_code_id):
    """
    生成图片验证码
    1/调用captcha扩展实现生成图片验证码
    2/在本地存储图片验证码,放到redis中,
    3/如果存储异常,需要终止程序执行
    4/返回图片验证码
    :return:
    """
    # 调用扩展实现生成图片验证码
    name,text,image = captcha.generate_captcha()
    # 在本地存储图片验证码
    try:
        # 在redis中缓存图片验证码,设置图片验证码编号,设置过期时间
        redis_store.setex("ImageCode_" + image_code_id,constants.IMAGE_CODE_REDIS_EXPIRES,text)
    except Exception as e:
        # 使用应用上下文,记录日志信息
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg="保存图片验证码异常")
    else:
        # 调用flask内置的响应对象,返回图片验证码
        response = make_response(image)
        return response


@api.route('/smscode/<mobile>',methods=['GET'])
def send_sms_code(mobile):
    """
    发送短信验证码:获取参数/校验参数/查询数据/返回结果
    1/获取参数:用户输入的图片验证码和图片验证码编号
    2/校验参数:mobile,image_code,image_code_id必须存在
    3/进一步校验参数的正确,mobile,正则校验手机号格式
    4/获取本地redis中存储的真实图片验证码,校验查询结果,
    5/比较图片验证码是否正确
    6/生成短信验证码,使用random模块
    7/调用云通信接口,实现发送短信,mobile,sms_code,temp_id;
    8/保存发送短信接口的返回结果
    9/返回前端发送结果
    :param mobile:
    :return:
    """
    # 获取参数,text为用户输入的图片验证码内容,id为图片验证码编号
    image_code = request.args.get('text')
    image_code_id = request.args.get('id')
    # 校验参数
    # if mobile and image_code and image_code_id:
    # any表示一个存在
    if not all([mobile,image_code,image_code_id]):
        return jsonify(errno=RET.PARAMERR,errmsg="参数缺失")
    # 进一步校验参数
    if not re.match(r"^1[34578]\d{9}$",mobile):
        return jsonify(errno=RET.PARAMERR,errmsg="手机号格式错误")
    # 获取本地存储的真实图片验证码
    try:
        real_image_code = redis_store.get("ImageCode_" + image_code_id)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg="获取图片验证码失败")
    # 校验查询结果
    if not real_image_code:
        return jsonify(errno=RET.DATAERR,errmsg="图片验证码过期")
    # 删除图片验证码
    try:
        redis_store.delete("ImageCode_" + image_code_id)
    except Exception as e:
        current_app.logger.error(e)
    # 比较图片验证码是否一致,一般图片验证码需要进行忽略大小写
    if real_image_code.lower() != image_code.lower():
        return jsonify(errno=RET.DATAERR,errmsg="图片验证码输入错误")
    # 判断用户是否注册
    try:
        # 通过精确查询判断用户手机号是否注册
        user = User.query.filter_by(mobile=mobile).first()
    except Exception as e:
        current_app.logger.error(e)
    else:
        # 判断查询结果手机号存在
        if user is not None:
            return jsonify(errno=RET.DBERR,errmsg="手机号已注册")
    # 图片验证码输入正确后,需要构造短信验证码
    sms_code = "%06d" % random.randint(0,999999)
    # 缓存短信验证码
    try:
        redis_store.setex("SMSCode_" + mobile,constants.SMS_CODE_REDIS_EXPIRES,sms_code)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg="保存短信验证码失败")
    try:
        # 实例化云通信发送短信接口对象,调用发送短信方法
        ccp = sms.CCP()
        result = ccp.send_template_sms(mobile,[sms_code,constants.SMS_CODE_REDIS_EXPIRES/60],1)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.THIRDERR,errmsg="发送短信失败")
    # 判断发送短信的返回结果
    # if result = 0:
    #     pass
    # 变量写在后面
    if 0 == result:
        return jsonify(errno=RET.OK,errmsg="发送成功")
    else:
        return jsonify(errno=RET.THIRDERR,errmsg="发送失败")


@api.route('/users',methods=['POST'])
def register():
    """
    注册:
    1/获取参数,mobile,sms_code,password,get_json()
    2/校验参数存在
    3/进一步获取详细的参数信息
    4/校验参数完整性
    5/手机号格式校验
    6/短信验证码校验,在redis中获取真实的短信验证码,校验结果
    7/比较短信验证码
    8/存储用户信息,user = User(name=mobile,mobile=mobile),user.password = password
    9/缓存用户信息
    10/返回结果,返回用户user.to_dict()
    :return:
    """
    # 获取前端post请求发送的参数
    user_data = request.get_json()
    # 校验参数
    if not user_data:
        return jsonify(errno=RET.PARAMERR,errmsg="参数错误")
    # 获取详细参数信息
    mobile = user_data.get('mobile')
    sms_code = user_data.get('sms_code')
    password = user_data.get("password")
    # 校验参数完整性
    if not all([mobile,sms_code,password]):
        return jsonify(errno=RET.PARAMERR,errmsg="参数缺失")
    # 校验手机号格式
    if not re.match(r"^1[34578]\d{9}$",mobile):
        return jsonify(errno=RET.PARAMERR,errmsg="手机号格式错误")
    # 获取本地存储的真实短信验证码
    try:
        real_sms_code = redis_store.get("SMSCode_" + mobile)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg="获取短信验证码失败")
    # 校验查询结果
    if not real_sms_code:
        return jsonify(errno=RET.DATAERR,errmsg="短信验证码过期")
    # 比较短信验证码
    if real_sms_code != str(sms_code):
        return jsonify(errno=RET.DATAERR,errmsg="短信验证码错误")
    # 删除短信验证码
    try:
        redis_store.delete("SMSCode_" + mobile)
    except Exception as e:
        current_app.logger.error(e)
    # 存储用户信息
    user = User(name=mobile,mobile=mobile)
    # 调用了模型类中的属性,实现密码加密存储
    user.password = password
    # 存储用户信息到数据库
    try:
        db.session.add(user)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        # 保存信息失败,需要进行回滚
        db.session.rollback()
        return jsonify(errno=RET.DBERR,errmsg="保存用户信息失败")
    # 缓存用户信息到redis中
    session["user_id"] = user.id
    session["name"] = mobile
    session["mobile"] = mobile
    # 返回注册结果
    return jsonify(errno=RET.OK,errmsg="OK",data=user.to_dict())
