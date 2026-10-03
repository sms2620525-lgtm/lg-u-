package space.jarvis.remote;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.os.*;
import android.content.pm.PackageManager;
import android.bluetooth.*;
import android.bluetooth.le.*;
import android.hardware.*;
import android.graphics.Color;
import android.view.WindowManager;
import android.widget.*;
import java.nio.*;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.*;

@SuppressLint("MissingPermission") // Every BLE entry point is gated by hasPermissions().
public class MainActivity extends Activity implements SensorEventListener {
    static final UUID SERVICE=UUID.fromString("78e7a600-7d35-4aa1-8b5f-565445c90001");
    static final UUID AUTH=UUID.fromString("78e7a600-7d35-4aa1-8b5f-565445c90002");
    static final UUID MOTION=UUID.fromString("78e7a600-7d35-4aa1-8b5f-565445c90003");
    static final UUID CCCD=UUID.fromString("00002902-0000-1000-8000-00805f9b34fb");
    SensorManager sensors; Sensor sensor; BluetoothManager manager;
    volatile BluetoothGattServer server; BluetoothLeAdvertiser advertiser;
    BluetoothGattCharacteristic motion;
    volatile BluetoothDevice authorized;
    volatile boolean subscribed=false, pending=false, started=false;
    volatile String pin=""; volatile long pinExpiry=0; volatile int attempts=0;
    TextView status, code; long last=0;
    void message(String text){runOnUiThread(()->status.setText(text));}
    @Override public void onCreate(Bundle state){
        super.onCreate(state);getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        LinearLayout layout=new LinearLayout(this);layout.setOrientation(LinearLayout.VERTICAL);layout.setPadding(40,90,40,40);layout.setBackgroundColor(Color.rgb(6,9,22));
        TextView title=new TextView(this);title.setText("JARVIS\nBluetooth Motion");title.setTextSize(28);title.setTextColor(Color.rgb(150,235,240));layout.addView(title);
        TextView guide=new TextView(this);guide.setText("휴대폰이 3D 컨트롤러가 됩니다.\n전송 시작 → 맥에서 휴대폰 검색 → 아래 코드 입력\nWi-Fi와 인터넷은 필요하지 않아요.\n");layout.addView(guide);
        code=new TextView(this);code.setText("------");code.setTextSize(40);layout.addView(code);
        Button start=new Button(this);start.setText("Bluetooth 전송 시작");layout.addView(start);Button stop=new Button(this);stop.setText("전송 중단");layout.addView(stop);
        status=new TextView(this);status.setPadding(0,24,0,0);status.setText("연결 대기 중");layout.addView(status);setContentView(layout);
        sensors=(SensorManager)getSystemService(SENSOR_SERVICE);sensor=sensors.getDefaultSensor(Sensor.TYPE_GAME_ROTATION_VECTOR);if(sensor==null)sensor=sensors.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR);
        manager=(BluetoothManager)getSystemService(BLUETOOTH_SERVICE);
        start.setOnClickListener(v->{if(!hasPermissions()){requestPermissions(new String[]{Manifest.permission.BLUETOOTH_ADVERTISE,Manifest.permission.BLUETOOTH_CONNECT},1);return;}begin();});
        stop.setOnClickListener(v->{end();message("전송을 멈췄어요.");});
    }
    boolean hasPermissions(){return Build.VERSION.SDK_INT<31||(checkSelfPermission(Manifest.permission.BLUETOOTH_ADVERTISE)==PackageManager.PERMISSION_GRANTED&&checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT)==PackageManager.PERMISSION_GRANTED);}
    @Override public void onRequestPermissionsResult(int request,String[] permissions,int[] results){super.onRequestPermissionsResult(request,permissions,results);if(hasPermissions())begin();else message("주변 기기 권한을 허용해야 연결할 수 있어요.");}
    void begin(){
        end();if(sensor==null){message("회전 센서가 없는 휴대폰입니다.");return;}
        BluetoothAdapter adapter=manager==null?null:manager.getAdapter();if(adapter==null||!adapter.isEnabled()){message("휴대폰 설정에서 Bluetooth를 켜 주세요.");return;}
        advertiser=adapter.getBluetoothLeAdvertiser();if(advertiser==null){message("이 휴대폰은 BLE 전송을 지원하지 않습니다.");return;}
        pin=String.format(Locale.US,"%06d",new SecureRandom().nextInt(1000000));pinExpiry=SystemClock.elapsedRealtime()+300000;attempts=0;code.setText(pin);
        server=manager.openGattServer(this,callback);if(server==null){message("Bluetooth 서버를 열지 못했어요.");return;}
        BluetoothGattService service=new BluetoothGattService(SERVICE,BluetoothGattService.SERVICE_TYPE_PRIMARY);
        service.addCharacteristic(new BluetoothGattCharacteristic(AUTH,BluetoothGattCharacteristic.PROPERTY_WRITE,BluetoothGattCharacteristic.PERMISSION_WRITE));
        motion=new BluetoothGattCharacteristic(MOTION,BluetoothGattCharacteristic.PROPERTY_NOTIFY,0);
        motion.addDescriptor(new BluetoothGattDescriptor(CCCD,BluetoothGattDescriptor.PERMISSION_READ|BluetoothGattDescriptor.PERMISSION_WRITE));service.addCharacteristic(motion);
        started=true;message("Bluetooth 준비 중…");if(!server.addService(service)){end();message("Bluetooth 서비스를 등록하지 못했어요.");return;}
        sensors.registerListener(this,sensor,SensorManager.SENSOR_DELAY_GAME);
    }
    final AdvertiseCallback advertiseCallback=new AdvertiseCallback(){
        @Override public void onStartSuccess(AdvertiseSettings settings){message("맥에서 휴대폰을 검색하고 코드를 입력하세요.\n코드는 5분 동안 유효해요.");}
        @Override public void onStartFailure(int error){runOnUiThread(()->{end();message("Bluetooth 광고 실패: "+error);});}
    };
    final BluetoothGattServerCallback callback=new BluetoothGattServerCallback(){
        @Override public void onServiceAdded(int result,BluetoothGattService service){
            if(!started||server==null)return;
            if(result!=BluetoothGatt.GATT_SUCCESS){runOnUiThread(()->{end();message("서비스 등록 실패");});return;}
            AdvertiseSettings settings=new AdvertiseSettings.Builder().setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY).setConnectable(true).setTxPowerLevel(AdvertiseSettings.ADVERTISE_TX_POWER_MEDIUM).build();
            AdvertiseData data=new AdvertiseData.Builder().addServiceUuid(new ParcelUuid(SERVICE)).build();
            advertiser.startAdvertising(settings,data,advertiseCallback);
        }
        @Override public void onConnectionStateChange(BluetoothDevice device,int result,int state){
            if(state==BluetoothProfile.STATE_DISCONNECTED&&device.equals(authorized)){authorized=null;subscribed=false;pending=false;message("연결이 끊어졌어요. 전송 시작을 다시 눌러 주세요.");}
        }
        @Override public void onCharacteristicWriteRequest(BluetoothDevice device,int id,BluetoothGattCharacteristic characteristic,boolean prepared,boolean response,int offset,byte[] value){
            BluetoothGattServer g=server;if(g==null)return;boolean ok=false;
            if(AUTH.equals(characteristic.getUuid())&&!prepared&&offset==0&&authorized==null&&attempts<5&&SystemClock.elapsedRealtime()<pinExpiry){attempts++;ok=pin.equals(new String(value,StandardCharsets.US_ASCII));if(ok){authorized=device;message("맥에 연결됨 · 휴대폰을 기울여 보세요.");}}
            if(response)g.sendResponse(device,id,ok?BluetoothGatt.GATT_SUCCESS:BluetoothGatt.GATT_FAILURE,0,null);
        }
        @Override public void onDescriptorReadRequest(BluetoothDevice device,int id,int offset,BluetoothGattDescriptor descriptor){
            BluetoothGattServer g=server;if(g==null)return;
            boolean ok=offset==0&&CCCD.equals(descriptor.getUuid())&&device.equals(authorized);
            g.sendResponse(device,id,ok?BluetoothGatt.GATT_SUCCESS:BluetoothGatt.GATT_FAILURE,0,ok?(subscribed?BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE:BluetoothGattDescriptor.DISABLE_NOTIFICATION_VALUE):null);
        }
        @Override public void onDescriptorWriteRequest(BluetoothDevice device,int id,BluetoothGattDescriptor descriptor,boolean prepared,boolean response,int offset,byte[] value){
            BluetoothGattServer g=server;if(g==null)return;
            boolean ok=CCCD.equals(descriptor.getUuid())&&device.equals(authorized)&&!prepared&&offset==0&&(Arrays.equals(value,BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE)||Arrays.equals(value,BluetoothGattDescriptor.DISABLE_NOTIFICATION_VALUE));
            if(ok)subscribed=Arrays.equals(value,BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);
            if(response)g.sendResponse(device,id,ok?BluetoothGatt.GATT_SUCCESS:BluetoothGatt.GATT_FAILURE,0,null);
        }
        @Override public void onNotificationSent(BluetoothDevice device,int result){pending=false;}
    };
    @Override public void onSensorChanged(SensorEvent event){
        BluetoothGattServer g=server;BluetoothDevice device=authorized;
        if(!started||g==null||device==null||!subscribed||pending||event.timestamp-last<50000000)return;
        last=event.timestamp;float[] matrix=new float[9],angles=new float[3];SensorManager.getRotationMatrixFromVector(matrix,event.values);SensorManager.getOrientation(matrix,angles);
        byte[] bytes=ByteBuffer.allocate(8).order(ByteOrder.LITTLE_ENDIAN).putFloat((float)Math.toDegrees(angles[1])).putFloat((float)Math.toDegrees(angles[2])).array();
        pending=true;
        if(Build.VERSION.SDK_INT>=33){if(g.notifyCharacteristicChanged(device,motion,false,bytes)!=BluetoothStatusCodes.SUCCESS)pending=false;}
        else{motion.setValue(bytes);if(!g.notifyCharacteristicChanged(device,motion,false))pending=false;}
    }
    @Override public void onAccuracyChanged(Sensor sensor,int accuracy){}
    void end(){started=false;if(sensors!=null)sensors.unregisterListener(this);if(hasPermissions()){if(advertiser!=null)advertiser.stopAdvertising(advertiseCallback);BluetoothGattServer g=server;server=null;if(g!=null)g.close();}authorized=null;subscribed=false;pending=false;pin="";if(code!=null)code.setText("------");}
    @Override public void onPause(){end();super.onPause();if(status!=null)status.setText("전송 중단됨 · 시작을 눌러 다시 연결하세요.");}
}
