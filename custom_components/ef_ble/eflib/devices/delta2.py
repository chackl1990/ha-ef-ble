from ..devicebase import DeviceBase
from ..model import (
    AllKitDetailData,
    DirectBmsMDeltaHeartbeatPack,
    DirectBmsMHeartbeatPack,
    DirectEmsDeltaHeartbeatPack,
    DirectInvDelta2HeartbeatPack,
    Mr330MpptHeart,
    Mr330PdHeart,
)
from ..packet import Packet
from ..props import Field
from ..props.raw_data_field import dataclass_attr_mapper, raw_field
from ..props.raw_data_props import RawDataProps

pb_pd = dataclass_attr_mapper(Mr330PdHeart)
pb_mppt = dataclass_attr_mapper(Mr330MpptHeart)
pb_ems = dataclass_attr_mapper(DirectEmsDeltaHeartbeatPack)
pb_bms_master = dataclass_attr_mapper(DirectBmsMDeltaHeartbeatPack)
pb_bms_slave = dataclass_attr_mapper(DirectBmsMHeartbeatPack)
pb_inv = dataclass_attr_mapper(DirectInvDelta2HeartbeatPack)
# pb = proto_attr_mapper(pd335_sys_pb2.DisplayPropertyUpload)

_PD100_BACKUP_REVERSE_SOC_FIELD = 461
_PD100_ACP_CHG_POW_MAX_FIELD = 107
_PD100_ACP_CHG_POW_HAL_MAX_FIELD = 108

_PD100_CFG_BACKUP_REVERSE_SOC_FIELD = 102
_PD100_CFG_ACP_CHG_POW_MAX_FIELD = 246
_PD100_CFG_AC_IN_CHG_MODE_FIELD = 125

_PD100_ENERGY_BACKUP_EN_FIELD = 7
_PD100_CMS_MAX_CHG_SOC_FIELD = 270
_PD100_CMS_MIN_DSG_SOC_FIELD = 271
_PD100_CONFIG_READ_ACTION_FIELD = 1
_PD100_CONFIG_READ_ACTION_DISPLAY = 41
_PD100_CONFIG_READ_ACTION_BACKUP = 144
_PD100_AC_IN_CHG_MODE_SELF_DEF_POW = 0


class Device(DeviceBase, RawDataProps):
    """Delta 2"""

    SN_PREFIX = (b"R331", b"R335")
    NAME_PREFIX = "EF-R33"
    _master_bms_msg: DirectBmsMDeltaHeartbeatPack | None
    _slave_bms_msg: DirectBmsMHeartbeatPack | None

    @property
    def packet_version(self):
        return 2

    ac_output_power = raw_field(pb_inv.output_watts)
    ac_input_power = raw_field(pb_pd.ac_input_watts)
    plugged_in_ac = raw_field(pb_pd.ac_charge_flag, lambda x: x == 1)

    battery_level_main = raw_field(pb_bms_master.f32_show_soc, lambda x: round(x, 2))
    battery_level_slave = raw_field(pb_bms_slave.f32_show_soc, lambda x: round(x, 2))
    battery_level = Field[float]()

    master_design_cap = raw_field(pb_bms_master.design_cap)
    master_remain_cap = raw_field(pb_bms_master.remain_cap)
    slave_design_cap = raw_field(pb_bms_slave.design_cap)
    slave_remain_cap = raw_field(pb_bms_slave.remain_cap)

    input_power = raw_field(pb_pd.watts_in_sum)
    output_power = raw_field(pb_pd.watts_out_sum)

    usbc_output_power = raw_field(pb_pd.typec1_watts)
    usba_output_power = raw_field(pb_pd.usb1_watt)

    usb_ports = raw_field(pb_pd.dc_out_state, lambda x: x == 1)

    battery_charge_limit_min = raw_field(pb_ems.min_dsg_soc)
    battery_charge_limit_max = raw_field(pb_ems.max_charge_soc)

    cell_temperature = raw_field(pb_pd.car_temp)

    dc_12v_port = raw_field(pb_pd.car_state, lambda x: x == 1)
    dc_output_power = raw_field(pb_pd.dc_pv_output_watts)
    dc12v_output_voltage = raw_field(pb_mppt.car_out_vol, lambda x: round(x / 1000, 2))
    dc12v_output_current = raw_field(pb_mppt.car_out_amp, lambda x: round(x / 1000, 2))

    ac_ports = raw_field(pb_pd.cfg_ac_enabled, lambda x: x == 1)

    # ac_charging_speed = raw_field(pb_mppt.cfg_chg_watts)
    # max_ac_charging_power = Field[int]()
    # min_ac_charging_power = Field[int]()

    # energy_backup = raw_field(pb.energy_backup_en)
    # energy_backup_battery_level = raw_field(pb.energy_backup_start_soc)
    energy_backup_battery_level = raw_field(pb_pd.bp_power_soc)

    def _update_battery_level(self) -> None:
        total_design = (self.master_design_cap or 0) + (self.slave_design_cap or 0)
        total_remain = (self.master_remain_cap or 0) + (self.slave_remain_cap or 0)

        new_value: float | None = None
        if total_design:
            new_value = round((total_remain / total_design) * 100, 2)
        elif (
            self.battery_level_main is not None and self.battery_level_slave is not None
        ):
            new_value = round(
                (self.battery_level_main + self.battery_level_slave) / 2, 2
            )
        elif self.battery_level_main is not None:
            new_value = self.battery_level_main
        elif self.battery_level_slave is not None:
            new_value = self.battery_level_slave

        if new_value is not None:
            self.battery_level = new_value

    def _set_bms_soc_value(
        self,
        msg: DirectBmsMHeartbeatPack | DirectBmsMDeltaHeartbeatPack | None,
        field_name: str,
    ) -> None:
        if msg is None:
            return
        value = self._determine_bms_soc(msg)
        if value is None:
            return
        setattr(self, field_name, value)

    @staticmethod
    def _determine_bms_soc(
        msg: DirectBmsMHeartbeatPack | DirectBmsMDeltaHeartbeatPack,
    ) -> float | None:
        charging = (msg.input_watts or 0) > (msg.output_watts or 0)
        if charging and msg.f32_show_soc is not None:
            return round(msg.f32_show_soc, 2)
        if msg.soc is not None:
            return float(msg.soc)
        if msg.f32_show_soc is not None:
            return round(msg.f32_show_soc, 2)
        return None

    def __init__(self, ble_dev, adv_data, sn: str) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self._product_type: int | None = None
        self._master_bms_msg = None
        self._slave_bms_msg = None

    @classmethod
    def check(cls, sn):
        return sn[:4] in cls.SN_PREFIX

    @property
    def device(self):
        model = "2"
        match self._sn[:4]:
            case "D361":
                model = "3 1500"

        return f"Delta {model}"

    async def packet_parse(self, data: bytes) -> Packet:
        return Packet.fromBytes(data, is_xor=True)

    async def data_parse(self, packet: Packet) -> bool:
        """Process the incoming notifications from the device"""

        processed = False
        self.reset_updated()

        match packet.src, packet.cmdSet, packet.cmdId:
            case 0x02, 0x20, 0x02:
                self.update_from_bytes(Mr330PdHeart, packet.payload)
                processed = True
            case 0x03, 0x03, 0x0E:
                detail = self.update_from_bytes(AllKitDetailData, packet.payload)
                self._update_product_type(detail)
                processed = True
            case 0x03, 0x20, 0x02:
                self.update_from_bytes(DirectEmsDeltaHeartbeatPack, packet.payload)
                processed = True
            case 0x03, 0x20, 0x32:
                master_msg = self.update_from_bytes(
                    DirectBmsMDeltaHeartbeatPack, packet.payload
                )
                self._master_bms_msg = master_msg
                self._set_bms_soc_value(master_msg, "battery_level_main")
                processed = True
            case 0x06, 0x20, 0x32:
                slave_msg = self.update_from_bytes(
                    DirectBmsMHeartbeatPack, packet.payload
                )
                self._slave_bms_msg = slave_msg
                self._set_bms_soc_value(slave_msg, "battery_level_slave")
                processed = True
            case 0x04, _, 0x02:
                self.update_from_bytes(DirectInvDelta2HeartbeatPack, packet.payload)
                processed = True
            case 0x05, 0x20, 0x02:
                self.update_from_bytes(Mr330MpptHeart, packet.payload)
                processed = True

        if processed:
            self._update_battery_level()

        for field_name in self.updated_fields:
            self.update_callback(field_name)
            self.update_state(field_name, getattr(self, field_name))

        return processed

    async def set_battery_charge_limit_max(self, limit: int):
        packet = Packet(0x21, 0x03, 0x20, 0x31, limit.to_bytes(), version=0x02)
        await self._conn.sendPacket(packet)

    async def set_battery_charge_limit_min(self, limit: int):
        packet = Packet(0x21, 0x03, 0x20, 0x33, limit.to_bytes(), version=0x02)
        await self._conn.sendPacket(packet)

    # async def set_ac_charging_speed(self, value: int):
    #    if (
    #        self.max_ac_charging_power is None
    #        or value > 1200
    #        or value < 200
    #    ):
    #        return False
    #    packet = Packet(0x21, 0x02, 0xFE, 0x11, 0xB0, 0x03, _encode_varint(value), 0xE8, 0x07, 0x00)
    #    await self._conn.sendPacket(packet)

    async def set_energy_backup_battery_level(self, value: int):
        # if value < 15 or value > 100:
        # return False
        packet = Packet(0x21, 0xFE, 0x11, 0x02, 0x01, value.to_bytes(), version=0x13)
        await self._conn.sendPacket(packet)

    async def enable_usb_ports(self, enabled: bool):
        packet = Packet(0x21, 0x02, 0x20, 0x22, enabled.to_bytes(), version=0x02)
        await self._conn.sendPacket(packet)

    async def enable_dc_12v_port(self, enabled: bool):
        packet = Packet(
            0x21, self._dc_12v_dst(), 0x20, 0x51, enabled.to_bytes(), version=0x02
        )
        await self._conn.sendPacket(packet)

    async def enable_ac_ports(self, enabled: bool):
        payload = bytes([1 if enabled else 0, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])
        packet = Packet(0x21, 0x05, 0x20, 0x42, payload, version=0x02)
        await self._conn.sendPacket(packet)

    def _update_product_type(self, detail: AllKitDetailData) -> None:
        if not detail.kit_base_info:
            return
        sn_bytes = self._sn.encode()
        for kit in detail.kit_base_info:
            if kit.sn.rstrip(b"\x00") == sn_bytes:
                self._product_type = kit.product_type
                return
        self._product_type = detail.kit_base_info[0].product_type

    def _dc_12v_dst(self) -> int:
        return 0x07 if self._product_type == 82 else 0x05

    @staticmethod
    def _as_single_byte(value: int) -> bytes:
        return value.to_bytes(1, "little", signed=False)

    @staticmethod
    def _encode_pd100_config_field(field_number: int, value: int) -> bytes:
        return Device._encode_varint((field_number << 3) | 0) + Device._encode_varint(
            value
        )

    @staticmethod
    def _encode_varint(value: int) -> bytes:
        result = bytearray()
        while True:
            to_write = value & 0x7F
            value >>= 7
            if value:
                result.append(to_write | 0x80)
            else:
                result.append(to_write)
                break
        return bytes(result)

    @staticmethod
    def _encode_pd100_config_read_action(action_id: int) -> bytes:
        key = (_PD100_CONFIG_READ_ACTION_FIELD << 3) | 0
        return Device._encode_varint(key) + Device._encode_varint(action_id)

    @staticmethod
    def _encode_pd100_config_read_actions(action_ids: list[int]) -> bytes:
        payload = bytearray()
        for action_id in action_ids:
            payload.extend(Device._encode_pd100_config_read_action(action_id))
        return bytes(payload)

    @staticmethod
    def _parse_pd100_varint_fields(payload: bytes) -> dict[int, int]:
        idx = 0
        values: dict[int, int] = {}
        length = len(payload)

        while idx < length:
            key, idx = Device._decode_varint(payload, idx)
            field_number = key >> 3
            wire_type = key & 0x07

            if wire_type == 0:  # varint
                value, idx = Device._decode_varint(payload, idx)
                values[field_number] = value
            elif wire_type == 1:  # fixed64
                idx += 8
            elif wire_type == 2:  # length-delimited
                size, idx = Device._decode_varint(payload, idx)
                idx += size
            elif wire_type == 5:  # fixed32
                idx += 4
            else:
                break

        return values

    @staticmethod
    def _decode_varint(payload: bytes, idx: int) -> tuple[int, int]:
        shift = 0
        value = 0
        length = len(payload)
        while idx < length:
            byte = payload[idx]
            idx += 1
            value |= (byte & 0x7F) << shift
            if (byte & 0x80) == 0:
                break
            shift += 7
        return value, idx
